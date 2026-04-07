# MCP сервер и клиент для температур Wireen Board

Проект состоит из двух частей:

- `server.py` — MCP-сервер по `stdio`, который подписывается на MQTT Wireen Board и отдает данные через tools.
- `client.py` — простой Python-клиент, который запускает сервер как subprocess и вызывает его tools.

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
WB_MQTT_HOST=127.0.0.1
WB_MQTT_PORT=1883
WB_MQTT_TOPICS=["wb-msw-v4_12/Temperature","wb-msw-v4_13/Temperature"]
WB_MQTT_ALIASES={"wb-msw-v4_12/Temperature":"Kitchen","wb-msw-v4_13/Temperature":"Boiler room"}
```

Поддерживаемые переменные:

- `WB_MQTT_HOST` — адрес MQTT брокера.
- `WB_MQTT_PORT` — порт MQTT брокера.
- `WB_MQTT_USERNAME` — логин, если нужен.
- `WB_MQTT_PASSWORD` — пароль, если нужен.
- `WB_MQTT_CLIENT_ID` — client id для MQTT.
- `WB_MQTT_KEEPALIVE` — keepalive в секундах.
- `WB_MQTT_TOPICS` — список MQTT value topic-ов. Можно JSON-массивом или строкой через запятую.
- `WB_MQTT_ALIASES` — JSON-объект с алиасами.

Для `WB_MQTT_ALIASES` ключом может быть:

- `sensor_id`, например `wb-msw-v4_12/Temperature`
- полный MQTT topic, например `/devices/wb-msw-v4_12/controls/Temperature`

Для `WB_MQTT_TOPICS` можно указывать:

- короткий формат: `wb-msw-v4_40/Temperature`
- полный формат Wireen Board: `/devices/wb-msw-v4_40/controls/Temperature`

Если `WB_MQTT_TOPICS` не задан, сервер подписывается на общие шаблоны:

- `/devices/+/controls/+`
- `/devices/+/controls/+/meta/+`

Если `WB_MQTT_TOPICS` задан, сервер подписывается на указанные value topics и автоматически добавляет для каждого `.../meta/+`.

## MCP tools

- `mqtt_status` — статус MQTT, число найденных сенсоров и список подписок.
- `list_temperature_sensors` — список температурных датчиков.
- `get_latest_temperatures` — последние числовые значения.
- `get_temperature_sensor` — один датчик по `sensor_id`.

В ответе датчика теперь есть поле `alias`, если оно задано в `.env`.

## Запуск

```bash
python server.py
python client.py status
python client.py sensors
python client.py latest
python client.py sensor --sensor-id "wb-msw-v4_12/Temperature"
```

По умолчанию клиент ждёт `3` секунды после запуска сервера, чтобы MQTT успел подключиться и получить retained-сообщения. Это можно поменять:

```bash
python client.py latest --wait-seconds 5
```

Если нужно сделать несколько запросов подряд без нового MQTT-подключения на каждый вызов, используйте интерактивный режим:

```bash
python client.py shell --wait-seconds 5
```

Команды внутри shell:

- `tools`
- `status`
- `sensors`
- `latest`
- `sensor wb-msw-v4_40/Temperature`
- `exit`
