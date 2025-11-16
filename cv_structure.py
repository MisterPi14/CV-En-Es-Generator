from pydantic import BaseModel
from typing import List, Optional

class PersonalInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None

class Experience(BaseModel):
    title: str
    company: str
    duration: str
    description: str

class Education(BaseModel):
    degree: str
    institution: str
    year: str

class CVStructure(BaseModel):
    personal_info: PersonalInfo
    summary: Optional[str] = None
    experience: List[Experience] = []
    education: List[Education] = []
    skills: List[str] = []
    languages: List[str] = []
    certifications: List[str] = []
