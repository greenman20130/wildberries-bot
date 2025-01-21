from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import MetaData, select
from config import database_url
from models import Base, Product


engine = create_async_engine(database_url, echo=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session 

async def get_product_by_artikul(artikul: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product).filter(Product.artikul == artikul))
        return result.scalars().first()

async def create_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)