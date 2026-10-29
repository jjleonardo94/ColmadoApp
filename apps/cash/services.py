from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import AuditLog
from apps.cash.models import (
    CashRegister,
    CashShift,
    CashShiftStatus,
    CashMovement,
    CashMovementType,
    CashDenomination,
    CashShiftDenominationCount,
)

class CashService:
    @staticmethod
    @transaction.atomic
    def open_shift(register_id: int, cashier, initial_cash: Decimal, initial_notes: str = '', branch=None, branch_id: int = None) -> CashShift:
        """
        Abre un turno de caja para un cajero y registra el fondo inicial.
        """
        register = CashRegister.objects.get(pk=register_id, is_active=True)
        
        # Verificar si la caja o el cajero ya tienen un turno abierto
        existing = CashShift.objects.filter(register=register, status=CashShiftStatus.ABIERTO).first()
        if existing:
            raise ValidationError(
                f"La caja '{register.name}' ya tiene un turno abierto por {existing.cashier.username} desde {existing.opened_at.strftime('%d/%m/%Y %H:%M')}."
            )

        user_open = CashShift.objects.filter(cashier=cashier, status=CashShiftStatus.ABIERTO).first()
        if user_open:
            raise ValidationError(
                f"El usuario {cashier.username} ya tiene un turno activo en la caja '{user_open.register.name}'. Debe cerrarlo primero."
            )

        from apps.core.models import ColmadoBranch
        branch_obj = None
        if branch_id:
            branch_obj = ColmadoBranch.objects.filter(id=branch_id, is_active=True).first()
        elif branch:
            branch_obj = branch
        elif hasattr(cashier, 'profile'):
            allowed = cashier.profile.get_allowed_branches()
            branch_obj = allowed.first() if hasattr(allowed, 'first') else (allowed[0] if allowed else None)
        if not branch_obj:
            branch_obj = ColmadoBranch.get_default_branch()

        shift = CashShift.objects.create(
            branch=branch_obj,
            register=register,
            cashier=cashier,
            initial_cash=initial_cash,
            status=CashShiftStatus.ABIERTO,
            initial_notes=initial_notes,
        )

        # Movimiento de fondo inicial en caja
        if initial_cash > Decimal('0.00'):
            CashMovement.objects.create(
                shift=shift,
                movement_type=CashMovementType.INGRESO,
                category='FONDO_INICIAL',
                amount=initial_cash,
                description="Fondo inicial de apertura de turno",
                user=cashier,
            )

        AuditLog.objects.create(
            user=cashier,
            action='APERTURA_CAJA',
            target_model='CashShift',
            target_id=str(shift.id),
            details=f"Apertura de turno #{shift.id} en {register.name} con fondo RD$ {initial_cash:,.2f}",
        )
        return shift

    @staticmethod
    @transaction.atomic
    def close_shift(
        shift_id: int,
        user,
        denomination_counts: dict, # {denom_id: quantity}
        closing_notes: str = '',
        difference_explanation: str = '',
        cash_to_remain: Decimal = None,
        amount_withdrawn: Decimal = None,
        difference_authorized_by = None,
    ) -> CashShift:
        """
        Cierra un turno de caja con arqueo físico de denominaciones, validación de faltante/sobrante,
        separación de fondo retenido y retiro, y sellado inmutable del historial contable.
        """
        from apps.core.models import BusinessSettings
        settings = BusinessSettings.get_settings()

        shift = CashShift.objects.select_for_update().get(pk=shift_id)
        if shift.status == CashShiftStatus.CERRADO:
            raise ValidationError("Este turno de caja ya se encuentra cerrado.")

        expected = shift.calculate_current_expected_cash()
        
        # Conteo físico de billetes y monedas
        total_counted = Decimal('0.00')
        counts_to_create = []

        denominations = CashDenomination.objects.filter(is_active=True)
        for denom in denominations:
            raw_qty = denomination_counts.get(str(denom.id)) or denomination_counts.get(denom.id) or 0
            qty = int(raw_qty)
            if qty > 0:
                sub = Decimal(qty) * denom.value
                total_counted += sub
                counts_to_create.append(
                    CashShiftDenominationCount(
                        shift=shift,
                        denomination=denom,
                        quantity=qty,
                        subtotal=sub,
                    )
                )

        difference = total_counted - expected

        # Si hay diferencia (sobrante o faltante), la explicación es obligatoria
        if abs(difference) > Decimal('0.01'):
            if not difference_explanation.strip():
                diff_type = "sobrante" if difference > 0 else "faltante"
                raise ValidationError(
                    f"Existe una diferencia de RD$ {abs(difference):,.2f} ({diff_type}). "
                    "Debe ingresar una justificación detallada del motivo de la diferencia para poder cerrar el turno."
                )

        # Fondos al cierre
        if cash_to_remain is None:
            cash_to_remain = settings.default_closing_cash_fund
        
        if amount_withdrawn is None:
            amount_withdrawn = max(Decimal('0.00'), total_counted - cash_to_remain)

        # Guardar conteo físico
        CashShiftDenominationCount.objects.filter(shift=shift).delete()
        CashShiftDenominationCount.objects.bulk_create(counts_to_create)

        # Obtener conciliación para sellado histórico
        audit_summary = shift.get_sales_audit_summary()

        # Cerrar el turno y sellar snapshot inmutable
        shift.status = CashShiftStatus.CERRADO
        shift.closed_at = timezone.now()
        shift.closed_by = user
        shift.expected_cash = expected
        shift.counted_cash = total_counted
        shift.difference = difference
        shift.difference_explanation = difference_explanation
        shift.difference_authorized_by = difference_authorized_by
        shift.cash_to_remain = cash_to_remain
        shift.amount_withdrawn = amount_withdrawn
        shift.closing_notes = closing_notes
        
        # Snapshot inmutable
        shift.snapshot_credit_sales = audit_summary['fiado_sales']
        shift.snapshot_transfer_sales = audit_summary['transfer_sales']
        shift.snapshot_card_sales = audit_summary['card_sales']
        shift.snapshot_cash_sales = audit_summary['cash_sales']
        shift.snapshot_cash_abonos = audit_summary['abonos_cash']
        shift.snapshot_transfer_abonos = audit_summary['abonos_transfer']
        shift.snapshot_card_abonos = audit_summary['abonos_card']
        shift.snapshot_expenses = audit_summary['cash_expenses']
        shift.is_snapshot_sealed = True
        
        shift.save()

        AuditLog.objects.create(
            user=user,
            action='CIERRE_CAJA',
            target_model='CashShift',
            target_id=str(shift.id),
            details=(
                f"Cierre de caja #{shift.id}. Esperado: RD$ {expected:,.2f}, Contado: RD$ {total_counted:,.2f}, "
                f"Diferencia: RD$ {difference:,.2f}, Permanece en caja: RD$ {cash_to_remain:,.2f}, Retirado: RD$ {amount_withdrawn:,.2f}. "
                f"Explicación: {difference_explanation or 'Cuadre exacto'}"
            ),
        )

        return shift
