from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, date, timezone
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json
import re

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

# Define Models
class Contract(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    client: str
    start_date: date
    expiry_date: date
    status: str = "Active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ContractCreate(BaseModel):
    name: str
    client: str
    start_date: date
    expiry_date: date
    status: str = "Active"

class ContractUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = None

class DocumentAnalysisRequest(BaseModel):
    document_text: str

class DocumentAnalysisResponse(BaseModel):
    contract_date: Optional[str] = None
    contract_tenure: Optional[str] = None
    expiry_date: Optional[str] = None
    error: Optional[str] = None

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
    return [Contract(**parse_from_mongo(contract)) for contract in contracts]

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

# Health check
@api_router.get("/")
async def root():
    return {"message": "Contract Management API is running"}

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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()