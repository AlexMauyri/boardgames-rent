# gRPC-сервис вычислений

Отдельный процесс (TLS, порт `GRPC_PORT`, по умолчанию 50051), который выполняет
вычисления, не относящиеся к CRUD-логике основного API. FastAPI вызывает его
через gRPC; контракт описан в `proto/`.

| Сервис | `.proto` | RPC | Доступ к БД |
|---|---|---|---|
| `recommendation.v1.RecommendationService` | `proto/recommendation/v1/recommendation.proto` | `GetSimilarGames`, `GetPersonalRecommendations` | читает PostgreSQL как `reader_user` |
| `pricing.v1.PricingService` | `proto/pricing/v1/pricing.proto` | `CalculatePrice` | нет |
| `matching.v1.MatchingService` | `proto/matching/v1/matching.proto` | `RankGames` | нет |

Сервисы `pricing` и `matching` не ходят в БД: вызывающая сторона передаёт всё
необходимое в запросе. Так остаются чистыми функциями, которые тестируются без
БД, а правила доступности коробок остаются только в бэкенде.

## PricingService.CalculatePrice

Вход: состав заказа (тариф за сутки и залог каждой коробки) и длительность
аренды в сутках. Суммы передаются десятичными строками (`"300.00"`), а не
`double`, чтобы не накапливать ошибки округления.

- промежуточная сумма = сумма суточных тарифов × число суток;
- скидка за срок аренды: от 3 суток — 5 %, от 7 — 10 %, от 14 — 15 %
  (`app/pricing/calculator.py`, `DISCOUNT_TIERS`);
- итог = промежуточная сумма − скидка, округление до копеек (half-up);
- залог = сумма залогов коробок, от срока и скидки не зависит.

Пустой заказ, срок меньше суток, нечисловая или отрицательная сумма →
`INVALID_ARGUMENT`.

В бэкенде вызывается из `create_order` (`POST /orders`) и из
`POST /orders/quote`. Если сервис недоступен, бэкенд отвечает `503`: цена
молча не пересчитывается локально без скидки, иначе клиент платил бы разную
сумму в зависимости от доступности сервиса.

## MatchingService.RankGames

Подбор игры под параметры встречи («4 игрока, до 1,5 часов, пункт „Центр“»).
Вход: число игроков, лимит времени в минутах, любимые категории (необязательно)
и список кандидатов — игр, у которых есть свободная коробка, с остатками
в выбранном пункте и в других пунктах.

Отбрасываются игры, у которых число игроков вне допустимого диапазона, нет
свободных коробок или время партии больше лимита более чем на 25 %. Остальные
получают оценку от 0 до 1 как взвешенное среднее (`app/matching/scoring.py`):

| Критерий | Вес | Суть |
|---|---|---|
| время | 0,30 | полный балл, если игра укладывается в лимит и занимает не меньше половины; падает до 0 при превышении лимита на 25 % |
| число игроков | 0,25 | лучше всего, когда компания в середине диапазона игры |
| категории | 0,25 | доля любимых категорий, которые покрывает игра; критерий исключается, если предпочтений нет |
| наличие | 0,20 | коробка в пункте — 1,0, нужна доставка — 0,6 |

Причина (`reason`): `fits_meeting`, `category_match`, `needs_delivery` или
`slightly_long`. Порядок: оценка по убыванию, затем игры «на полке» вперёд,
затем `game_id`.

В бэкенде вызывается из `GET /catalog/match`. Если сервис недоступен,
используется обычный фильтр (оценка 0, причина `fallback_filter`).

## Запуск

Сервис работает по TLS. Сертификаты для разработки (CA и серверный сертификат
для хостов `grpc` и `localhost`) создаёт скрипт, результат кладётся в
`infra/grpc_certs` (каталог в `.gitignore`, монтируется в контейнеры `grpc`
и `backend`):

```bash
bash infra/grpc/gen-certs.sh
docker compose up
```

В `.env` должно быть `GRPC_RECOMMENDATION_ADDR=grpc:50051`.

## Заглушки protobuf

После изменения `.proto`:

```bash
cd services/grpc
uv run --group dev bash scripts/generate_proto.sh
cd ../backend
bash scripts/sync_proto.sh
```

## Тесты

```bash
docker compose --profile test run --rm grpc-test
```

Тесты `test_pricing_calculator`, `test_matching_scoring`, `test_service_pricing`
и `test_service_matching` не требуют БД и запускаются локально:
`uv run pytest tests/test_pricing_calculator.py tests/test_matching_scoring.py tests/test_service_pricing.py tests/test_service_matching.py`
(нужны переменные `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — любые значения).
