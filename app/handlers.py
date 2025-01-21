from aiogram import types, F, Router
from aiogram.types import Message
from aiogram.filters import Command
from database import get_product_by_artikul
from models import Product
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import Depends


router = Router()

@router.message(Command("start"))
async def start_handler(msg: Message):
    await msg.answer("Привет! Введите артикул товара для получения данных.")

@router.message()
async def message_handler(msg: types.Message):
    artikul = msg.text.strip()
    product = await get_product_by_artikul(artikul = artikul)

    if product:
        response = (
            f"Название: {product.name}\n"
            f"Артикул: {product.artikul}\n"
            f"Цена: {product.price} руб.\n"
            f"Рейтинг: {product.rating}\n"
            f"Суммарное количество: {product.total_quantity}\n"
        )
    else:
        response = "Товар не найден."

    await msg.reply(response)