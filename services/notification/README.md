# Notification Service

Отдельный процесс (порт 8001), который доставляет клиентам события из RabbitMQ
в реальном времени по WebSocket.

```
API Service ──publish──▶ RabbitMQ (exchange boardgame.events, topic)
                              │ queue "notifications", binding "#"
                              ▼
                     Notification Service ──WebSocket /ws──▶ клиент
```

## События

API Service публикует события после коммита транзакции; если брокер
недоступен, запрос всё равно выполняется (событие логируется как потерянное).
Routing key равен типу события.

| Тип | Когда | Кому уведомление |
|---|---|---|
| `order.created` | оформлен заказ | клиенту заказа |
| `order.status_changed` | отмена, в пути, готов к выдаче, выдан, завершён | клиенту заказа |
| `delivery.created` | заказу нужна доставка | всем подключённым курьерам |
| `delivery.status_changed` | принята, в пути, доставлена | всем подключённым курьерам |
| `delivery.cancelled` | клиент отменил заказ до начала доставки | всем подключённым курьерам |

Конверт: `{"id", "type", "occurred_at", "data"}`. Тексты уведомлений и выбор
получателей находятся в `app/events.py`. Уведомление отправляется только тем,
кто подключён в момент события; пропущенные пользователь увидит через REST.

## WebSocket `/ws`

1. Клиент подключается и первым сообщением в течение
   `WS_AUTH_TIMEOUT_SECONDS` (5 с) отправляет
   `{"type": "auth", "token": "<access JWT>"}`. Токен не передаётся в URL,
   чтобы он не попадал в логи nginx.
2. Сервис проверяет подпись (`JWT_SECRET`), срок действия и тип `access`,
   отвечает `{"type": "ready", "role": "...", "user_id": 1}`.
3. Дальше приходят уведомления:
   `{"id", "type", "title", "message", "data", "created_at"}`.
4. Неверный или отсутствующий токен: закрытие с кодом `4401`.
5. `{"type": "ping"}` → `{"type": "pong"}`.

Через nginx доступно как `ws://localhost/ws`.

## Клиентское приложение

```bash
uv run python scripts/listen.py --token <access JWT>
```

Токен берётся из ответа `POST /api/v1/auth/login`. Скрипт печатает
уведомления в консоль и работает как отдельный процесс.

## Тесты

```bash
uv run pytest
```

В Docker: `docker compose --profile test run --rm notification-test`.
