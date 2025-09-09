from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Email configuration
GMAIL_EMAIL = os.environ.get('GMAIL_EMAIL')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')

# Define Models
class Contract(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    client: str
    contact_email: EmailStr
    start_date: date
    expiry_date: date
    status: str = "Active"
    last_reminder_sent: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ContractCreate(BaseModel):
    name: str
    client: str
    contact_email: EmailStr
    start_date: date
    expiry_date: date
    status: str = "Active"

class ContractUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = None

class ContractRenewal(BaseModel):
    new_expiry_date: date
    contact_email: Optional[EmailStr] = None

class DocumentAnalysisRequest(BaseModel):
    document_text: str

class DocumentAnalysisResponse(BaseModel):
    contract_date: Optional[str] = None
    contract_tenure: Optional[str] = None
    expiry_date: Optional[str] = None
    error: Optional[str] = None

# Email service functions
def send_email(to_email: str, subject: str, body: str, is_html: bool = False):
    """Send email using Gmail SMTP"""
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = GMAIL_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Gmail SMTP configuration
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Enable security
        server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(GMAIL_EMAIL, to_email, text)
        server.quit()
        
        logging.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {str(e)}")
        return False

def create_reminder_email(contract_name: str, client_name: str, expiry_date: str, days_remaining: int):
    """Create HTML email content for contract expiry reminder"""
    
    if days_remaining <= 0:
        urgency_class = "expired"
        urgency_text = "EXPIRED"
        message = f"Your contract '{contract_name}' with {client_name} has expired on {expiry_date}. Please take immediate action to renew or review this contract."
    elif days_remaining <= 7:
        urgency_class = "critical"
        urgency_text = "CRITICAL"
        message = f"Your contract '{contract_name}' with {client_name} will expire in {days_remaining} day{'s' if days_remaining != 1 else ''} on {expiry_date}. Immediate attention required!"
    elif days_remaining <= 30:
        urgency_class = "warning"
        urgency_text = "WARNING"
        message = f"Your contract '{contract_name}' with {client_name} will expire in {days_remaining} days on {expiry_date}. Please start renewal process."
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .content {{ padding: 30px; }}
            .alert {{ padding: 15px; border-radius: 5px; margin: 20px 0; font-weight: bold; text-align: center; }}
            .alert.warning {{ background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }}
            .alert.critical {{ background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
            .alert.expired {{ background-color: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }}
            .contract-details {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
            .detail-label {{ font-weight: bold; color: #495057; }}
            .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔔 Contract Expiry Reminder</h1>
                <p>KrijoTech Contract Management</p>
            </div>
            
            <div class="content">
                <div class="alert {urgency_class}">
                    ⚠️ {urgency_text}: Contract Expiring Soon
                </div>
                
                <p>Dear Contract Manager,</p>
                
                <p>{message}</p>
                
                <div class="contract-details">
                    <h3>📋 Contract Details</h3>
                    <div class="detail-row">
                        <span class="detail-label">Contract Name:</span>
                        <span>{contract_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Client:</span>
                        <span>{client_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Expiry Date:</span>
                        <span>{expiry_date}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Days Remaining:</span>
                        <span>{days_remaining if days_remaining > 0 else 'EXPIRED'}</span>
                    </div>
                </div>
                
                <p><strong>📝 Action Required:</strong></p>
                <ul>
                    <li>Review contract terms and conditions</li>
                    <li>Contact {client_name} to discuss renewal</li>
                    <li>Update contract status in the system</li>
                    <li>Set new expiry date if renewed</li>
                </ul>
                
                <p>Please log into your KrijoTech Contract Management dashboard to take appropriate action.</p>
                
                <p>Best regards,<br>
                <strong>KrijoTech Contract Management System</strong></p>
            </div>
            
            <div class="footer">
                <p>This is an automated reminder from KrijoTech Contract Management System.</p>
                <p>Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_body

async def check_and_send_reminders():
    """Check for contracts needing reminders and send emails"""
    try:
        # Get current date
        today = datetime.now(timezone.utc).date()
        
        # Find contracts that need reminders (30 days before expiry)
        contracts = await db.contracts.find().to_list(None)
        
        for contract_data in contracts:
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
        logging.error(f"Error in reminder check: {str(e)}")

# Background task scheduler
def run_scheduler():
    """Run the email reminder scheduler"""
    schedule.every().day.at("09:00").do(lambda: asyncio.create_task(check_and_send_reminders()))
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Helper functions
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
    """Calculate expiry date from start date and tenure"""
    try:
        start_date = datetime.fromisoformat(start_date_str).date()
        
        # Parse tenure string
        tenure_lower = tenure_str.lower()
        
        if 'year' in tenure_lower:
            years = int(re.search(r'(\d+)', tenure_str).group(1))
            expiry_date = date(start_date.year + years, start_date.month, start_date.day)
        elif 'month' in tenure_lower:
            months = int(re.search(r'(\d+)', tenure_str).group(1))
            year = start_date.year + (start_date.month + months - 1) // 12
            month = (start_date.month + months - 1) % 12 + 1
            expiry_date = date(year, month, start_date.day)
        elif 'day' in tenure_lower:
            days = int(re.search(r'(\d+)', tenure_str).group(1))
            from datetime import timedelta
            expiry_date = start_date + timedelta(days=days)
        else:
            return None
            
        return expiry_date.isoformat()
    except Exception:
        return None

# Contract CRUD endpoints
@api_router.post("/contracts", response_model=Contract)
async def create_contract(input: ContractCreate):
    contract_dict = input.dict()
    contract_obj = Contract(**contract_dict)
    contract_data = prepare_for_mongo(contract_obj.dict())
    await db.contracts.insert_one(contract_data)
    return contract_obj

@api_router.get("/contracts", response_model=List[Contract])
async def get_contracts():
    contracts = await db.contracts.find().to_list(1000)
    parsed_contracts = []
    today = datetime.now(timezone.utc).date()
    
    for contract in contracts:
        parsed_contract = parse_from_mongo(contract)
        
        # Handle missing contact_email for old contracts
        if 'contact_email' not in parsed_contract:
            parsed_contract['contact_email'] = 'unknown@example.com'
        
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

@api_router.get("/contracts/{contract_id}", response_model=Contract)
async def get_contract(contract_id: str):
    contract = await db.contracts.find_one({"id": contract_id})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return Contract(**parse_from_mongo(contract))

@api_router.put("/contracts/{contract_id}", response_model=Contract)
async def update_contract(contract_id: str, input: ContractUpdate):
    contract = await db.contracts.find_one({"id": contract_id})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    update_data = {k: v for k, v in input.dict().items() if v is not None}
    update_data['updated_at'] = datetime.now(timezone.utc)
    
    prepared_data = prepare_for_mongo(update_data)
    
    await db.contracts.update_one(
        {"id": contract_id}, 
        {"$set": prepared_data}
    )
    
    updated_contract = await db.contracts.find_one({"id": contract_id})
    return Contract(**parse_from_mongo(updated_contract))

@api_router.post("/contracts/{contract_id}/renew", response_model=Contract)
async def renew_contract(contract_id: str, renewal: ContractRenewal):
    """Renew an expired contract with new expiry date"""
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
    return Contract(**parse_from_mongo(renewed_contract))

@api_router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str):
    result = await db.contracts.delete_one({"id": contract_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contract not found")
    return {"message": "Contract deleted successfully"}

# AI Document Analysis endpoint
@api_router.post("/analyze-document", response_model=DocumentAnalysisResponse)
async def analyze_document(request: DocumentAnalysisRequest):
    try:
        # Initialize LLM chat with Gemini
        chat = LlmChat(
            api_key=os.environ.get('EMERGENT_LLM_KEY'),
            session_id=f"contract-analysis-{uuid.uuid4()}",
            system_message="You are an AI assistant that extracts contract information from documents. You must respond with valid JSON only."
        ).with_model("gemini", "gemini-2.0-flash")
        
        # Create analysis prompt
        prompt = f"""
        Analyze the following contract text and extract the contract start date and tenure information.
        
        Contract Text:
        {request.document_text}
        
        You MUST respond with ONLY a valid JSON object in this exact format:
        {{
            "contractDate": "YYYY-MM-DD",
            "contractTenure": "X years" or "X months"
        }}
        
        If you cannot find the start date, use null for contractDate.
        If you cannot find the tenure, use null for contractTenure.
        
        Do not include any other text, explanations, or formatting. Only return the JSON object.
        """
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        logging.info(f"AI Response: {response}")
        
        # Clean the response - remove any markdown formatting or extra text
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response.replace('```json', '').replace('```', '').strip()
        elif cleaned_response.startswith('```'):
            cleaned_response = cleaned_response.replace('```', '').strip()
            
        # Try to find JSON in the response
        import re
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
            # Try to extract information manually using regex
            contract_date = None
            contract_tenure = None
            
            # Look for dates in the document text
            date_patterns = [
                r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b',
                r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b',
                r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, request.document_text, re.IGNORECASE)
                if match:
                    try:
                        date_str = match.group(1)
                        # Try to parse and convert to ISO format
                        from datetime import datetime
                        if '/' in date_str:
                            if len(date_str.split('/')[2]) == 4:  # MM/DD/YYYY
                                parsed_date = datetime.strptime(date_str, '%m/%d/%Y')
                            else:  # DD/MM/YY
                                parsed_date = datetime.strptime(date_str, '%d/%m/%y')
                        elif '-' in date_str:
                            parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                        else:  # Month DD, YYYY
                            parsed_date = datetime.strptime(date_str, '%B %d, %Y')
                        
                        contract_date = parsed_date.strftime('%Y-%m-%d')
                        break
                    except:
                        continue
            
            # Look for tenure information
            tenure_patterns = [
                r'(\d+)\s*year[s]?',
                r'(\d+)\s*month[s]?',
                r'period\s+of\s+(\d+)\s*year[s]?',
                r'term.*?(\d+)\s*year[s]?'
            ]
            
            for pattern in tenure_patterns:
                match = re.search(pattern, request.document_text, re.IGNORECASE)
                if match:
                    number = match.group(1)
                    if 'year' in pattern:
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
                    error="Could not extract contract information from the document."
                )
            
    except Exception as e:
        logging.error(f"Document analysis error: {str(e)}")
        return DocumentAnalysisResponse(
            error="Analysis failed. Please try again or enter dates manually."
        )

# Manual reminder trigger (for testing)
@api_router.post("/send-reminders")
async def trigger_reminders(background_tasks: BackgroundTasks):
    """Manually trigger reminder check (for testing purposes)"""
    background_tasks.add_task(check_and_send_reminders)
    return {"message": "Reminder check triggered"}

# Health check
@api_router.get("/")
async def root():
    return {"message": "KrijoTech Contract Management API is running"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Start email scheduler in background thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()