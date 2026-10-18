"""An explicit simulator, deliberately unable to make network requests or charge cards."""

from multifuncbot.core.errors import DomainError


class DemoPayments:
    targets = {"success": "paid", "failure": "payment_failed", "cancel": "cancelled"}

    def transition(self, current, outcome):
        target = self.targets.get(outcome)
        if target is None:
            raise DomainError("Неизвестный результат оплаты.", "Unknown payment outcome.")
        if current == target:
            return current
        if current not in ("awaiting_payment", "payment_failed"):
            raise DomainError("Заказ уже оплачен или закрыт.", "Order is already paid or closed.")
        return target
