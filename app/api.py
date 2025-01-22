from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, AsyncSessionLocal
from models import Product, Subscription, User as UserModel
from schemas import ProductCreate, ProductResponse
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import create_database
from auth import create_access_token, verify_password, hash_password, User, Token
from sqlalchemy.future import select
from bot import main
import asyncio
import logging
from logging_config import setup_logging
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import http_exception_handler
from exceptions import http_exception_handler

app = FastAPI()
scheduler = AsyncIOScheduler()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

setup_logging()
logger = logging.getLogger(__name__)

app.add_exception_handler(HTTPException, http_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def fetch_and_store_product(artikul: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={artikul}")
        data = response.json()

    if data['state'] != 0 or not data['data']['products']:
        return  # Продукт не найден

    product_data = data['data']['products'][0]

    async with AsyncSessionLocal() as session:
        existing_product = await session.execute(select(Product).filter(Product.artikul == artikul))
        existing_product = existing_product.scalars().first()

        if existing_product:
            existing_product.name = product_data['name']
            existing_product.price = product_data['salePriceU'] / 100
            existing_product.rating = product_data['supplierRating']
            existing_product.total_quantity = product_data['totalQuantity']
            await session.commit()
        else:
            new_product = Product(
                name=product_data['name'],
                artikul=artikul,
                price=product_data['salePriceU'] / 100,
                rating=product_data['supplierRating'],
                total_quantity=product_data['totalQuantity']
            )
            session.add(new_product)
            await session.commit() 

@app.get("/api/v1/products/{artikul}", response_model=ProductResponse)
async def get_product(artikul: str, token: str = Query(...), db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на товар с артикулом: {artikul}")
    try:
        existing_product = await db.execute(select(Product).filter(Product.artikul == artikul))
        existing_product = existing_product.scalars().first()

        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={artikul}")
            data = response.json()

        if data['state'] != 0 or not data['data']['products']:
            raise HTTPException(status_code=404, detail="Product not found")

        product_data = data['data']['products'][0]

        if existing_product:
            logger.info(f"Товар с артикулом {artikul} обновлен в БД")
            existing_product.name = product_data['name']
            existing_product.price = product_data['salePriceU'] / 100
            existing_product.rating = product_data['supplierRating']
            existing_product.total_quantity = product_data['totalQuantity']
            
            await db.commit()
            await db.refresh(existing_product)
            return existing_product
        
        else:
            new_product = Product(
                name=product_data['name'],
                artikul=artikul,
                price=product_data['salePriceU'] / 100,
                rating=product_data['rating'],
                total_quantity=product_data['totalQuantity']
            )
            
            db.add(new_product)
            await db.commit()
            await db.refresh(new_product)
            logger.info(f"Товар с артикулом {artikul} добавлен в БД")
            
            return new_product
    
    except Exception as e:
        logger.error(f"Ошибка при получении товара: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")

@app.get("/api/v1/subscribe/{artikul}")
async def subscribe_product(artikul: str, token: str = Query(...), db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос подписки на товар с артикулом: {artikul}")
    try:
        async with db as session: 
            existing_subscription = await session.execute(
                select(Subscription).filter(Subscription.artikul == artikul)
            )
            if existing_subscription.scalars().first():
                raise HTTPException(status_code=400, detail="Already subscribed")

            job = scheduler.add_job(
                fetch_and_store_product,
                IntervalTrigger(minutes=30),
                args=[artikul],
                id=artikul,
                replace_existing=True
            )

            new_subscription = Subscription(artikul=artikul)
            session.add(new_subscription)
            await session.commit()
        logger.info(f"Создана подписка на товар с артикулом: {artikul}")
        return {"message": f"Subscribed to updates for product {artikul}"}
    
    except Exception as e:
        logger.error(f"Ошибка при создании подписки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")


@app.on_event("startup")
async def startup_event():
    logger.info("Запуск приложения")
    await create_database()
    async with AsyncSessionLocal() as session:
        existing_user = await session.execute(select(UserModel).filter(UserModel.username == 'admin'))
        if not existing_user.scalars().first():
            hashed_password = hash_password('passwd')
            new_user = UserModel(username='admin', hashed_password=hashed_password)
            session.add(new_user)
            await session.commit()
            print("Пользователь 'admin' для OAuth2 создан.", flush=True)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Subscription))
        subscriptions = result.scalars().all()
        for subscription in subscriptions:
            scheduler.add_job(
                fetch_and_store_product,
                IntervalTrigger(minutes=30),
                args=[subscription.artikul],
                id=subscription.artikul,
                replace_existing=True
            )
    
    scheduler.start()
    
    asyncio.create_task(main())
    logger.info("Приложение запущено")

@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    logger.info(f"Генерация токена для {form_data.username}")
    user = await db.execute(select(UserModel).filter(UserModel.username == form_data.username))
    user = user.scalars().first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
