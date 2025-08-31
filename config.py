import os

# ѕытаемс€ получить токен из переменных окружени€ (дл€ Heroku)
# ≈сли не найдено, используем локальный токен
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8344303909:AAEOIyIfyR-zz-q1z4CqbSF6UGO2YGvplj0')