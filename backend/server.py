from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, validator
from typing import List, Optional
import uuid
from datetime import datetime, date, timezone, timedelta
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
import threading
import schedule
import time
from functools import wraps

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection with error handling
try:
    mongo_url = os.environ['MONGO_URL']
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[os.environ['DB_NAME']]
except Exception as e:
    logging.error(f"Failed to connect to MongoDB: {str(e)}")
    raise

# Create the main app without a prefix
app = FastAPI(
    title="KrijoTech Contract Management API",
    description="AI-powered contract management with automated email reminders",
    version="1.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Email configuration with validation
GMAIL_EMAIL = os.environ.get('GMAIL_EMAIL')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')

if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
    logging.warning("Gmail credentials not found. Email functionality will be disabled.")

# Enhanced error handling decorator
def handle_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")
    return wrapper

# Enhanced Models with validation
class Contract(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=255)
    client: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr
    start_date: date
    expiry_date: date
    status: str = Field(default="Active", regex="^(Active|Expired|Renewed)$")
    last_reminder_sent: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @validator('expiry_date')
    def expiry_after_start(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('Expiry date must be after start date')
        return v

    @validator('name', 'client')
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

class ContractCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    client: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr
    start_date: date
    expiry_date: date
    status: str = Field(default="Active", regex="^(Active|Expired|Renewed)$")

    @validator('expiry_date')
    def expiry_after_start(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('Expiry date must be after start date')
        return v

    @validator('name', 'client')
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

class ContractUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    client: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_email: Optional[EmailStr] = None
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = Field(None, regex="^(Active|Expired|Renewed)$")

    @validator('name', 'client')
    def not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip() if v else v

class ContractRenewal(BaseModel):
    new_expiry_date: date
    contact_email: Optional[EmailStr] = None

    @validator('new_expiry_date')
    def future_date(cls, v):
        if v <= date.today():
            raise ValueError('New expiry date must be in the future')
        return v

class DocumentAnalysisRequest(BaseModel):
    document_text: str = Field(..., min_length=10, max_length=10000)

class DocumentAnalysisResponse(BaseModel):
    contract_date: Optional[str] = None
    contract_tenure: Optional[str] = None
    expiry_date: Optional[str] = None
    error: Optional[str] = None

# Enhanced email service functions with error handling
def send_email(to_email: str, subject: str, body: str, is_html: bool = False) -> bool:
    """Send email using Gmail SMTP with comprehensive error handling"""
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        logging.error("Gmail credentials not configured")
        return False
        
    try:
        # Validate email format
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', to_email):
            logging.error(f"Invalid email format: {to_email}")
            return False
            
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = GMAIL_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        if is_html:
            msg.attach(MIMEText(body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Gmail SMTP configuration with timeout
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.set_debuglevel(0)  # Disable debug output
        server.starttls()
        server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(GMAIL_EMAIL, to_email, text)
        server.quit()
        
        logging.info(f"Email sent successfully to {to_email}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        logging.error("SMTP authentication failed - check Gmail credentials")
        return False
    except smtplib.SMTPRecipientsRefused:
        logging.error(f"Recipient refused: {to_email}")
        return False
    except smtplib.SMTPServerDisconnected:
        logging.error("SMTP server disconnected unexpectedly")
        return False
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {str(e)}")
        return False

def create_reminder_email(contract_name: str, client_name: str, expiry_date: str, days_remaining: int) -> str:
    """Create enhanced HTML email content for contract expiry reminder"""
    
    if days_remaining <= 0:
        urgency_class = "expired"
        urgency_text = "EXPIRED"
        urgency_color = "#dc2626"
        message = f"Your contract '{contract_name}' with {client_name} has expired on {expiry_date}. Please take immediate action to renew or review this contract."
    elif days_remaining <= 7:
        urgency_class = "critical"
        urgency_text = "CRITICAL"
        urgency_color = "#ea580c"
        message = f"Your contract '{contract_name}' with {client_name} will expire in {days_remaining} day{'s' if days_remaining != 1 else ''} on {expiry_date}. Immediate attention required!"
    elif days_remaining <= 30:
        urgency_class = "warning"
        urgency_text = "WARNING"
        urgency_color = "#ca8a04"
        message = f"Your contract '{contract_name}' with {client_name} will expire in {days_remaining} days on {expiry_date}. Please start renewal process."
    
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Contract Expiry Reminder</title>
        <style>
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f8fafc; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 16px; overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); }}
            .header {{ background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); color: white; padding: 32px 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 28px; font-weight: 700; }}
            .header p {{ margin: 8px 0 0 0; opacity: 0.9; font-size: 16px; }}
            .content {{ padding: 32px 24px; }}
            .alert {{ padding: 20px; border-radius: 12px; margin: 24px 0; font-weight: 600; text-align: center; border: 2px solid {urgency_color}; background-color: {urgency_color}20; color: {urgency_color}; }}
            .contract-details {{ background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); padding: 24px; border-radius: 12px; margin: 24px 0; border: 1px solid #e2e8f0; }}
            .detail-row {{ display: flex; justify-content: space-between; align-items: center; margin: 12px 0; padding: 8px 0; border-bottom: 1px solid #e2e8f0; }}
            .detail-row:last-child {{ border-bottom: none; }}
            .detail-label {{ font-weight: 600; color: #475569; }}
            .detail-value {{ color: #1e293b; font-weight: 500; }}
            .action-list {{ background-color: #fef3c7; padding: 20px; border-radius: 12px; margin: 20px 0; border-left: 4px solid #f59e0b; }}
            .action-list h3 {{ margin: 0 0 12px 0; color: #92400e; }}
            .action-list ul {{ margin: 0; padding-left: 20px; }}
            .action-list li {{ margin: 8px 0; color: #78350f; }}
            .footer {{ background-color: #f8fafc; padding: 24px; text-align: center; color: #64748b; font-size: 14px; }}
            .brand {{ display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 12px; }}
            .brand-icon {{ width: 24px; height: 24px; background-color: #3b82f6; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔔 Contract Expiry Reminder</h1>
                <p>KrijoTech Contract Management System</p>
            </div>
            
            <div class="content">
                <div class="alert">
                    ⚠️ {urgency_text}: Contract Expiring Soon
                </div>
                
                <p style="font-size: 16px; line-height: 1.6; color: #374151;">Dear Contract Manager,</p>
                
                <p style="font-size: 16px; line-height: 1.6; color: #374151; margin: 16px 0;">{message}</p>
                
                <div class="contract-details">
                    <h3 style="margin: 0 0 16px 0; color: #1e293b; display: flex; align-items: center; gap: 8px;">
                        📋 Contract Details
                    </h3>
                    <div class="detail-row">
                        <span class="detail-label">Contract Name:</span>
                        <span class="detail-value">{contract_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Client:</span>
                        <span class="detail-value">{client_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Expiry Date:</span>
                        <span class="detail-value">{expiry_date}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Status:</span>
                        <span class="detail-value" style="color: {urgency_color};">
                            {days_remaining if days_remaining > 0 else 'EXPIRED'} days remaining
                        </span>
                    </div>
                </div>
                
                <div class="action-list">
                    <h3>📝 Immediate Actions Required:</h3>
                    <ul>
                        <li>Review contract terms and conditions</li>
                        <li>Contact {client_name} to discuss renewal options</li>
                        <li>Update contract status in the management system</li>
                        <li>Set new expiry date if contract is renewed</li>
                        <li>Archive contract documents if not renewing</li>
                    </ul>
                </div>
                
                <p style="font-size: 16px; line-height: 1.6; color: #374151; margin: 20px 0;">
                    Please log into your KrijoTech Contract Management dashboard to take appropriate action and update the contract status.
                </p>
                
                <p style="font-size: 16px; line-height: 1.6; color: #374151;">
                    Best regards,<br>
                    <strong>KrijoTech Contract Management System</strong>
                </p>
            </div>
            
            <div class="footer">
                <div class="brand">
                    <div class="brand-icon">K</div>
                    <strong>KrijoTech Contract Management</strong>
                </div>
                <p style="margin: 8px 0;">This is an automated reminder from your contract management system.</p>
                <p style="margin: 0; font-size: 12px;">Please do not reply to this email. For support, contact your system administrator.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_body

async def check_and_send_reminders():
    """Enhanced reminder checking with comprehensive error handling"""
    try:
        today = datetime.now(timezone.utc).date()
        
        # Find contracts that need reminders
        contracts = await db.contracts.find().to_list(None)
        reminder_count = 0
        
        for contract_data in contracts:
            try:
                # Handle missing contact_email for old contracts
                if 'contact_email' not in contract_data:
                    contract_data['contact_email'] = 'unknown@example.com'
                    
                parsed_contract = parse_from_mongo(contract_data)
                contract = Contract(**parsed_contract)
                
                # Calculate days until expiry
                days_until_expiry = (contract.expiry_date - today).days
                
                # Check if reminder needed (within 30 days or expired)
                should_send_reminder = False
                
                if days_until_expiry <= 30:
                    # Check if we sent a reminder today already
                    last_reminder = contract.last_reminder_sent
                    if not last_reminder or last_reminder.date() < today:
                        should_send_reminder = True
                
                if should_send_reminder:
                    # Skip sending to unknown email addresses
                    if contract.contact_email == 'unknown@example.com':
                        logging.info(f"Skipping email for contract {contract.name} - no valid email")
                        continue
                        
                    # Create and send reminder email
                    subject = f"Contract Expiry Reminder: {contract.name}"
                    if days_until_expiry <= 0:
                        subject = f"URGENT - Contract EXPIRED: {contract.name}"
                    elif days_until_expiry <= 7:
                        subject = f"CRITICAL - Contract Expires in {days_until_expiry} days: {contract.name}"
                    
                    email_body = create_reminder_email(
                        contract.name,
                        contract.client,
                        contract.expiry_date.strftime('%B %d, %Y'),
                        days_until_expiry
                    )
                    
                    # Send email
                    email_sent = send_email(
                        contract.contact_email,
                        subject,
                        email_body,
                        is_html=True
                    )
                    
                    if email_sent:
                        # Update last reminder sent timestamp
                        await db.contracts.update_one(
                            {"id": contract.id},
                            {"$set": {"last_reminder_sent": datetime.now(timezone.utc).isoformat()}}
                        )
                        reminder_count += 1
                        logging.info(f"Reminder sent for contract: {contract.name}")
                    else:
                        logging.error(f"Failed to send reminder for contract: {contract.name}")
                    
                    # Update status to expired if past due
                    if days_until_expiry <= 0 and contract.status != "Expired":
                        await db.contracts.update_one(
                            {"id": contract.id},
                            {"$set": {"status": "Expired"}}
                        )
                        logging.info(f"Contract status updated to Expired: {contract.name}")
                        
            except Exception as e:
                logging.error(f"Error processing contract {contract_data.get('name', 'unknown')}: {str(e)}")
                continue
                
        logging.info(f"Reminder check completed. Sent {reminder_count} reminders.")
                    
    except Exception as e:
        logging.error(f"Error in reminder check: {str(e)}")

# Background task scheduler with error handling
def run_scheduler():
    """Run the email reminder scheduler with error recovery"""
    schedule.every().day.at("09:00").do(lambda: asyncio.create_task(check_and_send_reminders()))
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logging.error(f"Scheduler error: {str(e)}")
            time.sleep(300)  # Wait 5 minutes on error

# Enhanced helper functions
def prepare_for_mongo(data):
    """Convert Python date objects to ISO strings for MongoDB storage"""
    if isinstance(data.get('start_date'), date):
        data['start_date'] = data['start_date'].isoformat()
    if isinstance(data.get('expiry_date'), date):
        data['expiry_date'] = data['expiry_date'].isoformat()
    if isinstance(data.get('created_at'), datetime):
        data['created_at'] = data['created_at'].isoformat()
    if isinstance(data.get('updated_at'), datetime):
        data['updated_at'] = data['updated_at'].isoformat()
    if isinstance(data.get('last_reminder_sent'), datetime):
        data['last_reminder_sent'] = data['last_reminder_sent'].isoformat()
    return data

def parse_from_mongo(item):
    """Convert ISO strings back to Python date objects"""
    if isinstance(item.get('start_date'), str):
        item['start_date'] = datetime.fromisoformat(item['start_date']).date()
    if isinstance(item.get('expiry_date'), str):
        item['expiry_date'] = datetime.fromisoformat(item['expiry_date']).date()
    if isinstance(item.get('created_at'), str):
        item['created_at'] = datetime.fromisoformat(item['created_at'])
    if isinstance(item.get('updated_at'), str):
        item['updated_at'] = datetime.fromisoformat(item['updated_at'])
    if isinstance(item.get('last_reminder_sent'), str):
        item['last_reminder_sent'] = datetime.fromisoformat(item['last_reminder_sent'])
    return item

def calculate_expiry_date(start_date_str: str, tenure_str: str) -> Optional[str]:
    """Calculate expiry date from start date and tenure with enhanced parsing"""
    try:
        start_date = datetime.fromisoformat(start_date_str).date()
        
        # Enhanced tenure parsing
        tenure_lower = tenure_str.lower()
        
        # Extract number from tenure string
        numbers = re.findall(r'\d+', tenure_str)
        if not numbers:
            return None
            
        number = int(numbers[0])
        
        if any(word in tenure_lower for word in ['year', 'yr', 'annual']):
            expiry_date = date(start_date.year + number, start_date.month, start_date.day)
        elif any(word in tenure_lower for word in ['month', 'mo', 'monthly']):
            year = start_date.year + (start_date.month + number - 1) // 12
            month = (start_date.month + number - 1) % 12 + 1
            expiry_date = date(year, month, start_date.day)
        elif any(word in tenure_lower for word in ['day', 'daily']):
            expiry_date = start_date + timedelta(days=number)
        elif any(word in tenure_lower for word in ['week', 'weekly']):
            expiry_date = start_date + timedelta(weeks=number)
        else:
            # Default to months if unclear
            year = start_date.year + (start_date.month + number - 1) // 12
            month = (start_date.month + number - 1) % 12 + 1
            expiry_date = date(year, month, start_date.day)
            
        return expiry_date.isoformat()
    except Exception as e:
        logging.error(f"Error calculating expiry date: {str(e)}")
        return None

# Enhanced Contract CRUD endpoints
@api_router.post("/contracts", response_model=Contract)
@handle_errors
async def create_contract(input: ContractCreate):
    """Create a new contract with enhanced validation"""
    contract_dict = input.dict()
    contract_obj = Contract(**contract_dict)
    contract_data = prepare_for_mongo(contract_obj.dict())
    
    try:
        await db.contracts.insert_one(contract_data)
        logging.info(f"Contract created: {contract_obj.name}")
        return contract_obj
    except Exception as e:
        logging.error(f"Failed to create contract: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create contract")

@api_router.get("/contracts", response_model=List[Contract])
@handle_errors
async def get_contracts():
    """Get all contracts with automatic status updates"""
    try:
        contracts = await db.contracts.find().to_list(1000)
        parsed_contracts = []
        today = datetime.now(timezone.utc).date()
        
        for contract in contracts:
            # Handle missing contact_email for old contracts
            if 'contact_email' not in contract:
                contract['contact_email'] = 'unknown@example.com'
                
            parsed_contract = parse_from_mongo(contract)
            contract_obj = Contract(**parsed_contract)
            
            # Auto-update status to expired if past due date
            if contract_obj.expiry_date < today and contract_obj.status != "Expired":
                contract_obj.status = "Expired"
                await db.contracts.update_one(
                    {"id": contract_obj.id},
                    {"$set": {"status": "Expired"}}
                )
            
            parsed_contracts.append(contract_obj)
        
        return parsed_contracts
    except Exception as e:
        logging.error(f"Failed to fetch contracts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch contracts")

@api_router.get("/contracts/{contract_id}", response_model=Contract)
@handle_errors
async def get_contract(contract_id: str):
    """Get a single contract by ID"""
    try:
        contract = await db.contracts.find_one({"id": contract_id})
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
            
        # Handle missing contact_email for old contracts
        if 'contact_email' not in contract:
            contract['contact_email'] = 'unknown@example.com'
            
        return Contract(**parse_from_mongo(contract))
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to fetch contract {contract_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch contract")

@api_router.put("/contracts/{contract_id}", response_model=Contract)
@handle_errors
async def update_contract(contract_id: str, input: ContractUpdate):
    """Update a contract with validation"""
    try:
        contract = await db.contracts.find_one({"id": contract_id})
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        update_data = {k: v for k, v in input.dict().items() if v is not None}
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        # Validate date relationship if both dates are being updated
        if 'start_date' in update_data and 'expiry_date' in update_data:
            if update_data['expiry_date'] <= update_data['start_date']:
                raise HTTPException(status_code=422, detail="Expiry date must be after start date")
        
        prepared_data = prepare_for_mongo(update_data)
        
        await db.contracts.update_one(
            {"id": contract_id}, 
            {"$set": prepared_data}
        )
        
        updated_contract = await db.contracts.find_one({"id": contract_id})
        return Contract(**parse_from_mongo(updated_contract))
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to update contract {contract_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update contract")

@api_router.post("/contracts/{contract_id}/renew", response_model=Contract)
@handle_errors
async def renew_contract(contract_id: str, renewal: ContractRenewal):
    """Renew an expired contract with new expiry date"""
    try:
        contract = await db.contracts.find_one({"id": contract_id})
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        # Update contract with new expiry date and reset status
        update_data = {
            'expiry_date': renewal.new_expiry_date.isoformat(),
            'status': 'Active',
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'last_reminder_sent': None  # Reset reminder tracking
        }
        
        # Update contact email if provided
        if renewal.contact_email:
            update_data['contact_email'] = renewal.contact_email
        
        await db.contracts.update_one(
            {"id": contract_id},
            {"$set": update_data}
        )
        
        renewed_contract = await db.contracts.find_one({"id": contract_id})
        logging.info(f"Contract renewed: {renewed_contract['name']}")
        return Contract(**parse_from_mongo(renewed_contract))
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to renew contract {contract_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to renew contract")

@api_router.delete("/contracts/{contract_id}")
@handle_errors
async def delete_contract(contract_id: str):
    """Delete a contract"""
    try:
        result = await db.contracts.delete_one({"id": contract_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Contract not found")
        logging.info(f"Contract deleted: {contract_id}")
        return {"message": "Contract deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete contract {contract_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete contract")

# Enhanced AI Document Analysis endpoint
@api_router.post("/analyze-document", response_model=DocumentAnalysisResponse)
@handle_errors
async def analyze_document(request: DocumentAnalysisRequest):
    """Analyze contract document with enhanced AI processing"""
    try:
        # Initialize LLM chat with Gemini
        chat = LlmChat(
            api_key=os.environ.get('EMERGENT_LLM_KEY'),
            session_id=f"contract-analysis-{uuid.uuid4()}",
            system_message="You are an AI assistant specialized in contract analysis. You must respond with valid JSON only."
        ).with_model("gemini", "gemini-2.0-flash")
        
        # Enhanced analysis prompt
        prompt = f"""
        Analyze the following contract text and extract the contract start date and tenure information.
        
        Contract Text:
        {request.document_text}
        
        You MUST respond with ONLY a valid JSON object in this exact format:
        {{
            "contractDate": "YYYY-MM-DD",
            "contractTenure": "X years" or "X months" or "X days"
        }}
        
        Instructions:
        - Extract the contract start date in YYYY-MM-DD format
        - Extract the contract duration/tenure (e.g., "1 year", "6 months", "24 months")
        - If you cannot find the start date, use null for contractDate
        - If you cannot find the tenure, use null for contractTenure
        - Look for phrases like "effective from", "starting", "commencing", "term of", "period of"
        - Be precise with date formats and tenure descriptions
        
        Do not include any other text, explanations, or formatting. Only return the JSON object.
        """
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        logging.info(f"AI Response: {response}")
        
        # Enhanced response cleaning
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response.replace('```json', '').replace('```', '').strip()
        elif cleaned_response.startswith('```'):
            cleaned_response = cleaned_response.replace('```', '').strip()
            
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', cleaned_response, re.DOTALL)
        if json_match:
            cleaned_response = json_match.group()
        
        # Parse the response
        try:
            response_data = json.loads(cleaned_response)
            contract_date = response_data.get('contractDate')
            contract_tenure = response_data.get('contractTenure')
            
            # Calculate expiry date if we have both start date and tenure
            expiry_date = None
            if contract_date and contract_tenure:
                expiry_date = calculate_expiry_date(contract_date, contract_tenure)
            
            return DocumentAnalysisResponse(
                contract_date=contract_date,
                contract_tenure=contract_tenure,
                expiry_date=expiry_date
            )
        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {e}, Response was: {cleaned_response}")
            
            # Enhanced fallback extraction using regex
            contract_date = None
            contract_tenure = None
            
            # Enhanced date patterns
            date_patterns = [
                r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b',
                r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b',
                r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
                r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b'
            ]
            
            for pattern in date_patterns:
                matches = re.finditer(pattern, request.document_text, re.IGNORECASE)
                for match in matches:
                    try:
                        date_str = match.group(0)
                        # Try multiple date formats
                        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%d %B %Y']:
                            try:
                                parsed_date = datetime.strptime(date_str, fmt)
                                contract_date = parsed_date.strftime('%Y-%m-%d')
                                break
                            except ValueError:
                                continue
                        if contract_date:
                            break
                    except Exception:
                        continue
                if contract_date:
                    break
            
            # Enhanced tenure patterns
            tenure_patterns = [
                r'(?:term|period|duration).*?(\d+)\s*(year[s]?)',
                r'(?:term|period|duration).*?(\d+)\s*(month[s]?)',
                r'(\d+)\s*(year[s]?)\s*(?:term|period|contract)',
                r'(\d+)\s*(month[s]?)\s*(?:term|period|contract)',
                r'(?:for|of)\s*(\d+)\s*(year[s]?)',
                r'(?:for|of)\s*(\d+)\s*(month[s]?)'
            ]
            
            for pattern in tenure_patterns:
                match = re.search(pattern, request.document_text, re.IGNORECASE)
                if match:
                    number = match.group(1)
                    unit = match.group(2).lower()
                    if 'year' in unit:
                        contract_tenure = f"{number} years" if int(number) > 1 else f"{number} year"
                    else:
                        contract_tenure = f"{number} months" if int(number) > 1 else f"{number} month"
                    break
            
            # Calculate expiry date if we have both
            expiry_date = None
            if contract_date and contract_tenure:
                expiry_date = calculate_expiry_date(contract_date, contract_tenure)
            
            if contract_date or contract_tenure:
                return DocumentAnalysisResponse(
                    contract_date=contract_date,
                    contract_tenure=contract_tenure,
                    expiry_date=expiry_date
                )
            else:
                return DocumentAnalysisResponse(
                    error="Could not extract contract information from the document. Please ensure the document contains clear date and duration information."
                )
            
    except Exception as e:
        logging.error(f"Document analysis error: {str(e)}")
        return DocumentAnalysisResponse(
            error="Analysis failed due to technical issues. Please try again or enter dates manually."
        )

# Enhanced reminder trigger endpoint
@api_router.post("/send-reminders")
@handle_errors
async def trigger_reminders(background_tasks: BackgroundTasks):
    """Manually trigger reminder check with comprehensive feedback"""
    try:
        background_tasks.add_task(check_and_send_reminders)
        logging.info("Manual reminder check triggered")
        return {"message": "Email reminder check has been triggered successfully"}
    except Exception as e:
        logging.error(f"Failed to trigger reminders: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to trigger reminder check")

# Health check with detailed status
@api_router.get("/health")
async def health_check():
    """Comprehensive health check"""
    try:
        # Test database connection
        await db.contracts.count_documents({})
        
        # Test email configuration
        email_configured = bool(GMAIL_EMAIL and GMAIL_APP_PASSWORD)
        
        return {
            "status": "healthy",
            "service": "KrijoTech Contract Management API",
            "database": "connected",
            "email_service": "configured" if email_configured else "not_configured",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0"
        }
    except Exception as e:
        logging.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# Root endpoint
@api_router.get("/")
async def root():
    return {
        "message": "KrijoTech Contract Management API is running",
        "version": "1.0.0",
        "features": [
            "AI-powered document analysis",
            "Automated email reminders",
            "Contract renewal management",
            "Real-time status tracking"
        ]
    }

# Include the router in the main app
app.include_router(api_router)

# Enhanced CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# Start email scheduler in background thread with error handling
try:
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Email reminder scheduler started successfully")
except Exception as e:
    logger.error(f"Failed to start scheduler: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logger.info("KrijoTech Contract Management API starting up...")
    
    # Test database connection
    try:
        await db.contracts.count_documents({})
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
    
    # Verify email configuration
    if GMAIL_EMAIL and GMAIL_APP_PASSWORD:
        logger.info("Email service configured")
    else:
        logger.warning("Email service not configured - reminders will be disabled")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logger.info("KrijoTech Contract Management API shutting down...")
    try:
        client.close()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")