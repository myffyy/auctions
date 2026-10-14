# Покрытие функционала тестами

Для требования ЛР3 «не менее 40% функционала ТЗ» единицей учёта выбран основной сценарий из раздела 3 [технического задания](technical-specification.md). В этом разделе семь сценариев. Для каждого ниже указаны автоматические проверки наблюдаемого результата и обязательных правил. Все семь сценариев имеют тесты (7/7); это не означает проверки всех возможных комбинаций входных данных, всех маршрутов или всего браузерного интерфейса.

| Сценарий ТЗ | Автоматические проверки |
| --- | --- |
| 1. Создание аукциона, порядок дат и UTC | `test_create_get_and_list_auctions`; `test_auction_schema_normalizes_time_to_utc`; `test_auction_schema_rejects_invalid_date_range`; `test_auction_schema_rejects_missing_timezone` |
| 2. Создание лота в существующем аукционе с положительной ценой | `test_create_get_and_list_lots`; `test_reject_lot_with_unknown_auction`; `test_reject_lot_with_unknown_seller`; `test_lot_schema_rejects_price_with_too_many_decimal_places`; `test_lot_schema_rejects_non_positive_price` |
| 3. Заявка на доступный лот, допустимая цена и одна pending-заявка | `test_request_at_starting_price_does_not_create_sale`; `test_reject_request_below_starting_price`; `test_reject_duplicate_pending_request`; `test_reject_request_for_sold_lot` |
| 4. Подтверждение администратором, продажа и доход, статусы и время | `test_buyer_request_requires_admin_approval`; `test_reject_repeated_review`; `test_buyer_cannot_review_request`; `test_failed_approval_keeps_request_pending`; `test_failed_sale_rolls_back_all_changes` |
| 5. Отклонение, история и доступность лота | `test_rejected_request_is_kept_and_allows_resubmission`; `test_reject_repeated_review` |
| 6. Однократная продажа, нижняя граница цены, комиссия и округление | `test_register_sale_rejects_repeated_sale`; `test_register_sale_rejects_price_below_starting`; `test_sale_at_starting_price_is_allowed`; `test_sale_price_and_commission`; `test_rejected_sale_has_no_writes` |
| 7. Служебный ответ `/health` | `test_health` |

Дополнительно проверяются создание и чтение участников, создание учётной записи и привязка профиля, ограничения доступа, вход и чтение продаж/доходов. Эти проверки находятся в `test_participants.py`, `test_web.py`, `test_authorization.py` и `test_sales_api.py`.

## Виды тестов и отчёты

- `make test-unit`: логика продажи с заменённой сессией PostgreSQL, валидация схем, безопасность тестовой конфигурации и ответ `/health`; сервер БД не требуется.
- `make test`: полный набор, включая HTTP API и настоящую отдельную PostgreSQL; отчёты JUnit, XML и HTML покрытия.
- `make test-mutations`: исходный код должен пройти unit-тесты; каждая из трёх контрольных подмен должна вызвать именно падение тестов. Ошибки сбора и пропуски не допускаются. Рабочий код не меняется.
- `make verify`: lock-файл, Ruff, SAST Bandit, полный набор с порогом покрытия и три контрольные мутации; дополнительно проверяются миграции на чистой и заполненной временных БД.

Покрытие кода измеряется отдельно от этой матрицы. Измеряется весь Python-код `src/auctions`, включая ветвления, без добавленных исключений файлов. Совокупный порог — 80%; отчёт также показывает покрытие строк и ветвей отдельно. Генерируемые отчёты находятся в `reports/` и не коммитятся.

## Границы и контрольные мутации

Цена ровно по начальной стоимости допустима; на копейку ниже — запрещена. Комиссия проверяется при 0%, 100%, дробном проценте и суммах до, на и после половины копейки. Схемы отклоняют нулевую и отрицательную цену, NaN/Infinity, лишние десятичные знаки, превышение максимальной суммы, неположительные ID и даты без часового пояса.

| Подмена | Ожидаемый тест, обнаруживающий её |
| --- | --- |
| Цена `<` заменена на `<=` | `test_sale_price_and_commission[100.00-10.00-10.00]` |
| `ROUND_HALF_UP` заменён на `ROUND_DOWN` | `test_sale_price_and_commission[100.05-10.00-10.01]` |
| Запрет продажи недоступного лота инвертирован | `test_rejected_sale_has_no_writes[sold_lot-LotAlreadySoldError]` и успешные продажи |

Эти три примера подтверждают чувствительность тестов к выбранным изменениям основной логики. Они не являются оценкой доли всех возможных мутаций проекта.
