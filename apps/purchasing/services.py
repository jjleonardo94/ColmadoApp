from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.inventory.services import InventoryService
from apps.inventory.models import MovementType
from apps.purchasing.models import Purchase, PurchaseStatus

class PurchaseService:
    @staticmethod
    @transaction.atomic
    def receive_purchase(purchase_id: int, user):
        """
        Confirma la recepción física de una compra y actualiza el inventario y costos.
        Garantiza idempotencia: si la compra ya fue recibida, no aumenta el inventario dos veces.
        """
        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
        if purchase.status == PurchaseStatus.RECIBIDA:
            raise ValidationError("Esta compra ya fue recibida previamente. No se puede recibir de nuevo.")
        if purchase.status == PurchaseStatus.ANULADA:
            raise ValidationError("No se puede recibir una compra que ha sido anulada.")

        ref_doc = f"Compra #{purchase.id} (Fact. {purchase.invoice_number or 'S/N'})"
        for item in purchase.items.select_related('product').all():
            product = item.product
            # Actualiza el costo unitario de compra del producto
            product.cost_price = item.unit_cost
            product.save(update_fields=['cost_price', 'updated_at'])

            # Registra la entrada al inventario
            InventoryService.process_movement(
                product_id=product.id,
                movement_type=MovementType.COMPRA,
                quantity=item.quantity,
                user=user,
                reason=f"Entrada por compra de mercancía a {purchase.supplier.name}",
                reference_doc=ref_doc
            )

        purchase.status = PurchaseStatus.RECIBIDA
        purchase.received_by = user
        purchase.received_at = timezone.now()
        purchase.save(update_fields=['status', 'received_by', 'received_at'])
        return purchase
