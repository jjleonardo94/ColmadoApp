from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.catalog.models import Product
from apps.core.models import BusinessSettings
from apps.inventory.models import InventoryMovement, MovementType

class InventoryService:
    @staticmethod
    @transaction.atomic
    def process_movement(product_id: int, movement_type: str, quantity: Decimal, user, reason: str = '', reference_doc: str = ''):
        """
        Ajusta el inventario de un producto dentro de una transacción atómica y con bloqueo pesimista
        para evitar condiciones de carrera (race conditions).
        """
        if quantity <= Decimal('0.000'):
            raise ValidationError("La cantidad debe ser mayor que cero.")

        product = Product.objects.select_for_update().get(pk=product_id)
        settings = BusinessSettings.get_settings()
        prev_stock = product.current_stock

        # Movimientos que suman stock
        incoming_types = [
            MovementType.COMPRA,
            MovementType.ANULACION_VENTA,
            MovementType.DEVOLUCION_CLIENTE,
            MovementType.AJUSTE_POSITIVO,
        ]

        if movement_type in incoming_types:
            new_stock = prev_stock + quantity
        else:
            # Movimientos que restan stock
            if not settings.allow_negative_stock and prev_stock < quantity:
                raise ValidationError(
                    f"Stock insuficiente para '{product.name}'. Disponible: {prev_stock}, Solicitado: {quantity}."
                )
            new_stock = prev_stock - quantity

        product.current_stock = new_stock
        product.save(update_fields=['current_stock', 'updated_at'])

        movement = InventoryMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            previous_stock=prev_stock,
            new_stock=new_stock,
            user=user,
            reason=reason,
            reference_doc=reference_doc,
        )
        return movement
