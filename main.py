# main.py
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import or_, and_, text

import re
import jinja2
import markdown
import uuid
import os

import os


# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./diary.db"
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DiaryEntry(Base):
    __tablename__ = "entries"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
env = templates.env
env.filters["markdown"] = lambda text: markdown.markdown(text)

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_entries(
    request: Request,
    db: Session = Depends(get_db),
    search: str = None,
    period: str = None,
    date: str = None
):
    query = db.query(DiaryEntry)
    
    if search:
        query = query.filter(DiaryEntry.title.ilike(f"%{search}%"))
    
    if period == "week":
        week_ago = datetime.now() - timedelta(days=7)
        query = query.filter(DiaryEntry.created_at >= week_ago)
    elif date:
        selected_date = datetime.strptime(date, "%Y-%m-%d")
        next_day = selected_date + timedelta(days=1)
        query = query.filter(and_(
            DiaryEntry.created_at >= selected_date,
            DiaryEntry.created_at < next_day
        ))
    
    entries = query.order_by(DiaryEntry.created_at.desc()).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "entries": entries,
        "search": search,
        "period": period,
        "selected_date": date
    })


@app.get("/create", response_class=HTMLResponse)
async def create_form(request: Request):
    return templates.TemplateResponse("create.html", {"request": request})

@app.post("/create")
async def create_entry(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    images: list[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    # Сохраняем изображения и заменяем ссылки в контенте
    content = await process_images(content, images)
    
    new_entry = DiaryEntry(title=title, content=content)
    db.add(new_entry)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/entry/{entry_id}", response_class=HTMLResponse)
async def read_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(DiaryEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return templates.TemplateResponse("entry.html", {
        "request": request,
        "entry": entry
    })

@app.get("/edit/{entry_id}", response_class=HTMLResponse)
async def edit_form(request: Request, entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(DiaryEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return templates.TemplateResponse("edit.html", {
        "request": request,
        "entry": entry
    })

@app.post("/edit/{entry_id}")
async def update_entry(
    request: Request,
    entry_id: int,
    title: str = Form(...),
    content: str = Form(...),
    images: list[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    entry = db.get(DiaryEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    content = await process_images(content, images, existing_content=entry.content)
    entry.title = title
    entry.content = content
    db.commit()
    
    return RedirectResponse(url=f"/entry/{entry_id}", status_code=303)

async def process_images(content: str, images: list[UploadFile], existing_content: str = None) -> str:
    image_urls = []
    
    if images:
        for image in images:
            if image.content_type not in ["image/jpeg", "image/png", "image/gif"]:
                continue
                
            filename = f"{uuid.uuid4().hex}.{image.content_type.split('/')[-1]}"
            filepath = os.path.join(UPLOAD_DIR, filename)
            
            with open(filepath, "wb") as buffer:
                buffer.write(await image.read())
            
            image_urls.append(f"/static/uploads/{filename}")
    
    # Сохраняем существующие изображения при редактировании
    if existing_content:
        existing_images = re.findall(r'\!\[.*?\]\((.*?)\)', existing_content)
        image_urls.extend(existing_images)
    
    # Добавляем новые изображения в конец контента
    for url in image_urls:
        content += f"\n\n![Image]({url})"
    
    return content


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)