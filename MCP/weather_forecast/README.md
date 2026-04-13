# MCP сервер прогноза погоды

Проект состоит из двух частей:

- `server.py` — MCP-сервер по `stdio`, который отдаёт текущую погоду и прогноз через tools.
- `client.py` — простой Python-клиент, который запускает сервер как subprocess и вызывает его tools.

В качестве источника данных используется Open-Meteo. По умолчанию API-ключ не нужен.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка через .env

Сервер автоматически читает файл `.env` из корня проекта.

Пример:

```env
WEATHER_DEFAULT_LANGUAGE=ru
WEATHER_DEFAULT_TIMEZONE=auto
WEATHER_DEFAULT_FORECAST_DAYS=5
WEATHER_TIMEOUT_SECONDS=20
WEATHER_USER_AGENT=my-weather-bot/1.0
```

Поддерживаемые переменные:

- `WEATHER_DEFAULT_LANGUAGE` — язык для геокодинга.
- `WEATHER_DEFAULT_TIMEZONE` — таймзона для прогноза. Рекомендуем `auto`.
- `WEATHER_DEFAULT_FORECAST_DAYS` — количество дней прогноза по умолчанию.
- `WEATHER_TIMEOUT_SECONDS` — таймаут HTTP-запросов.
- `WEATHER_USER_AGENT` — User-Agent для вызовов API.
- `WEATHER_GEOCODING_URL` — необязательная переопределённая ссылка на geocoding API.
- `WEATHER_FORECAST_URL` — необязательная переопределённая ссылка на forecast API.

## MCP tools

- `weather_status` — текущая конфигурация сервиса.
- `weather_geocode` — поиск населённого пункта и его координат.
- `get_current_weather` — текущая погода по `location` или координатам.
- `get_weather_forecast` — дневной прогноз и почасовой preview по `location` или координатам.

## Запуск

```bash
python server.py
python client.py status
python client.py geocode --location "Yekaterinburg"
python client.py current --location "Yekaterinburg"
python client.py forecast --location "Yekaterinburg" --days 5
python client.py current --latitude 56.8389 --longitude 60.6057
```

## Примеры аргументов tools

`weather_geocode`:

```json
{
  "location": "Yekaterinburg",
  "count": 3,
  "language": "ru"
}
```

`get_current_weather`:

```json
{
  "location": "Yekaterinburg",
  "timezone": "Asia/Yekaterinburg"
}
```

или

```json
{
  "latitude": 56.8389,
  "longitude": 60.6057
}
```

`get_weather_forecast`:

```json
{
  "location": "Yekaterinburg",
  "days": 5,
  "timezone": "Asia/Yekaterinburg"
}
```
