class PaymentStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    ALL = (PENDING, PROCESSING, PAID, FAILED, CANCELLED, REFUNDED)
    OPEN = (PENDING, PROCESSING)


class PaymentMethod:
    CASH = "cash"
    CARD_TAP = "card_tap"
    ORANGE_MONEY = "orange_money"
    MYZAKA = "myzaka"
    SMEGA = "smega"
    PAY_TO_CELL = "pay_to_cell"

    ALL = (CASH, CARD_TAP, ORANGE_MONEY, MYZAKA, SMEGA, PAY_TO_CELL)


class PaymentProviderName:
    NEXO_CASH = "nexo_cash"

    ALL = (NEXO_CASH,)


class PaymentCurrency:
    BWP = "BWP"


class SettlementStatus:
    DRIVER_COLLECTED = "driver_collected"
    NEXO_HELD = "nexo_held"
    SETTLED = "settled"
    NOT_APPLICABLE = "not_applicable"

    ALL = (DRIVER_COLLECTED, NEXO_HELD, SETTLED, NOT_APPLICABLE)


class RefundStatus:
    NONE = "none"
    PENDING = "pending"
    REFUNDED = "refunded"
    FAILED = "failed"

    ALL = (NONE, PENDING, REFUNDED, FAILED)


class PaymentFailureCode:
    AMOUNT_MISMATCH = "amount_mismatch"
