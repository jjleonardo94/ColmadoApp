import csv
import io
import json
from decimal import Decimal
from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
import xlsxwriter

from apps.sales.models import Sale, SaleItem, Payment, SaleStatus, PaymentMethodChoices
from apps.customers.models import Customer, CreditTransaction, CreditTransactionType
from apps.expenses.models import Expense, ExpenseCategory
from apps.catalog.models import Product, Category


def filter_sales_queryset(request):
    """
    Función unificada para filtrar ventas según parámetros GET del request.
    Reutilizada por el reporte web, la exportación CSV y la exportación Excel.
    """
    today = timezone.localdate()
    date_from_str = request.GET.get('desde')
    date_to_str = request.GET.get('hasta')

    # Por defecto, primer día del mes actual hasta hoy
    if not date_from_str:
        date_from_str = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_to_str:
        date_to_str = today.strftime('%Y-%m-%d')

    qs = Sale.objects.select_related('customer', 'cashier', 'cash_shift').prefetch_related('items__product').all()

    # Rango de fechas
    if date_from_str:
        qs = qs.filter(created_at__date__gte=date_from_str)
    if date_to_str:
        qs = qs.filter(created_at__date__lte=date_to_str)

    # Cliente
    customer_id = request.GET.get('cliente')
    if customer_id and customer_id.isdigit():
        qs = qs.filter(customer_id=customer_id)

    # Cajero / Usuario
    user_id = request.GET.get('usuario')
    if user_id and user_id.isdigit():
        qs = qs.filter(cashier_id=user_id)

    # Método de pago
    metodo = request.GET.get('metodo')
    if metodo:
        qs = qs.filter(payment_method=metodo)

    # Tipo de venta (Contado vs Crédito)
    tipo = request.GET.get('tipo')
    if tipo == 'CONTADO':
        qs = qs.filter(payment_method__in=[
            PaymentMethodChoices.EFECTIVO,
            PaymentMethodChoices.TRANSFERENCIA,
            PaymentMethodChoices.TARJETA
        ])
    elif tipo == 'CREDITO':
        qs = qs.filter(payment_method=PaymentMethodChoices.FIADO)

    # Origen / Canal
    origen = request.GET.get('origen')
    if origen:
        qs = qs.filter(origin=origen)

    # Estado
    estado = request.GET.get('estado')
    if estado:
        qs = qs.filter(status=estado)

    # Filtro por producto
    producto_id = request.GET.get('producto')
    if producto_id and producto_id.isdigit():
        qs = qs.filter(items__product_id=producto_id).distinct()

    # Filtro por categoría
    categoria_id = request.GET.get('categoria')
    if categoria_id and categoria_id.isdigit():
        qs = qs.filter(items__product__category_id=categoria_id).distinct()

    # Búsqueda libre (ticket, cliente)
    q = request.GET.get('q')
    if q:
        qs = qs.filter(
            Q(ticket_number__icontains=q) |
            Q(customer__name__icontains=q) |
            Q(customer__phone__icontains=q)
        )

    return qs, date_from_str, date_to_str


class ReportsDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        today = timezone.localdate()
        date_from_str = request.GET.get('desde')
        date_to_str = request.GET.get('hasta')

        start_date = today.replace(day=1)
        end_date = today

        if date_from_str:
            try:
                start_date = timezone.datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to_str:
            try:
                end_date = timezone.datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        sales_qs = Sale.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status=SaleStatus.COMPLETADA
        )

        total_sales = sales_qs.aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        transactions_count = sales_qs.count()

        sale_items = SaleItem.objects.filter(sale__in=sales_qs)
        total_cogs = sum(item.quantity * item.unit_cost for item in sale_items)
        gross_profit = total_sales - total_cogs
        gross_margin_pct = (gross_profit / total_sales * 100) if total_sales > 0 else Decimal('0.00')

        expenses_qs = Expense.objects.filter(date__gte=start_date, date__lte=end_date, is_paid=True)
        total_expenses = expenses_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        net_operating_profit = gross_profit - total_expenses

        # Cobros de abonos en el período
        abonos_collected = CreditTransaction.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            transaction_type=CreditTransactionType.ABONO_PAGO
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Ventas a crédito otorgadas en el período
        fiados_granted = sales_qs.filter(
            payment_method=PaymentMethodChoices.FIADO
        ).aggregate(t=Sum('total'))['t'] or Decimal('0.00')

        category_sales = SaleItem.objects.filter(sale__in=sales_qs).values(
            'product__category__name'
        ).annotate(
            total_amount=Sum('subtotal'),
            total_units=Sum('quantity')
        ).order_by('-total_amount')

        payment_breakdown = sales_qs.values(
            'payment_method'
        ).annotate(
            total_amount=Sum('total'),
            count=Count('id')
        ).order_by('-total_amount')

        expenses_breakdown = expenses_qs.values(
            'category__name'
        ).annotate(
            total_amount=Sum('amount')
        ).order_by('-total_amount')

        context = {
            'start_date': start_date,
            'end_date': end_date,
            'total_sales': total_sales,
            'transactions_count': transactions_count,
            'total_cogs': total_cogs,
            'gross_profit': gross_profit,
            'gross_margin_pct': gross_margin_pct,
            'total_expenses': total_expenses,
            'net_operating_profit': net_operating_profit,
            'abonos_collected': abonos_collected,
            'fiados_granted': fiados_granted,
            'category_sales': category_sales,
            'payment_breakdown': payment_breakdown,
            'expenses_breakdown': expenses_breakdown,
        }
        return render(request, 'reports/dashboard.html', context)


class SalesReportView(LoginRequiredMixin, View):
    def get(self, request):
        sales_qs, date_from_str, date_to_str = filter_sales_queryset(request)

        # Ventas completadas para cálculos de ingresos
        completed_sales = sales_qs.filter(status=SaleStatus.COMPLETADA)
        voided_sales = sales_qs.filter(status=SaleStatus.ANULADA)

        # 1. Resumen General
        total_sold = completed_sales.aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        sales_count = completed_sales.count()
        avg_sale = (total_sold / sales_count) if sales_count > 0 else Decimal('0.00')

        # Ventas Contado vs Crédito
        total_contado = completed_sales.filter(
            payment_method__in=[PaymentMethodChoices.EFECTIVO, PaymentMethodChoices.TRANSFERENCIA, PaymentMethodChoices.TARJETA]
        ).aggregate(t=Sum('total'))['t'] or Decimal('0.00')

        total_credito = completed_sales.filter(
            payment_method=PaymentMethodChoices.FIADO
        ).aggregate(t=Sum('total'))['t'] or Decimal('0.00')

        # Desglose por método de pago de ventas completadas
        efectivo_ventas = completed_sales.filter(payment_method=PaymentMethodChoices.EFECTIVO).aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        transferencia_ventas = completed_sales.filter(payment_method=PaymentMethodChoices.TRANSFERENCIA).aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        tarjeta_ventas = completed_sales.filter(payment_method=PaymentMethodChoices.TARJETA).aggregate(t=Sum('total'))['t'] or Decimal('0.00')

        # Total Descuentos aplicados
        total_discounts = completed_sales.aggregate(t=Sum('discount'))['t'] or Decimal('0.00')

        # Devoluciones / Anulaciones
        total_anuladas = voided_sales.aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        voided_count = voided_sales.count()

        # Abonos CxC en el período (se presentan de forma totalmente separada de las ventas)
        abonos_qs = CreditTransaction.objects.filter(
            transaction_type=CreditTransactionType.ABONO_PAGO
        )
        if date_from_str:
            abonos_qs = abonos_qs.filter(created_at__date__gte=date_from_str)
        if date_to_str:
            abonos_qs = abonos_qs.filter(created_at__date__lte=date_to_str)
        customer_id = request.GET.get('cliente')
        if customer_id and customer_id.isdigit():
            abonos_qs = abonos_qs.filter(customer_id=customer_id)

        total_abonos = abonos_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        abonos_efectivo = abonos_qs.filter(payment_method='EFECTIVO').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        abonos_transf = abonos_qs.filter(payment_method='TRANSFERENCIA').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        abonos_tarjeta = abonos_qs.filter(payment_method='TARJETA').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        # Dinero realmente ingresado en caja (Ventas contado efectivo + Abonos efectivo)
        dinero_efectivo_total = efectivo_ventas + abonos_efectivo

        # Ventas por Canal/Origen
        origen_pos = completed_sales.filter(origin='POS').aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        origen_wa = completed_sales.filter(origin='WHATSAPP').aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        origen_del = completed_sales.filter(origin='DELIVERY').aggregate(t=Sum('total'))['t'] or Decimal('0.00')

        # 2. Datos para Gráficos
        # Ventas por día
        daily_sales = completed_sales.values('created_at__date').annotate(
            day_total=Sum('total'),
            day_count=Count('id')
        ).order_by('created_at__date')

        chart_days_labels = [ds['created_at__date'].strftime('%d/%m') for ds in daily_sales]
        chart_days_values = [float(ds['day_total']) for ds in daily_sales]

        # Top 5 Productos más vendidos
        top_items = SaleItem.objects.filter(sale__in=completed_sales).values(
            'product__name'
        ).annotate(
            qty=Sum('quantity'),
            revenue=Sum('subtotal')
        ).order_by('-qty')[:5]

        top_products_labels = [item['product__name'] for item in top_items]
        top_products_quantities = [float(item['qty']) for item in top_items]

        # Catálogos para filtros
        customers = Customer.objects.all().order_by('name')
        cashiers = User.objects.filter(is_active=True).order_by('username')
        categories = Category.objects.all().order_by('name')
        products = Product.objects.all().order_by('name')

        context = {
            'sales': sales_qs.order_by('-created_at'),
            'date_from': date_from_str,
            'date_to': date_to_str,
            # Métricas
            'total_sold': total_sold,
            'sales_count': sales_count,
            'avg_sale': avg_sale,
            'total_contado': total_contado,
            'total_credito': total_credito,
            'total_discounts': total_discounts,
            'total_anuladas': total_anuladas,
            'voided_count': voided_count,
            # Métodos de Pago
            'efectivo_ventas': efectivo_ventas,
            'transferencia_ventas': transferencia_ventas,
            'tarjeta_ventas': tarjeta_ventas,
            # Abonos
            'total_abonos': total_abonos,
            'abonos_efectivo': abonos_efectivo,
            'abonos_transf': abonos_transf,
            'abonos_tarjeta': abonos_tarjeta,
            'dinero_efectivo_total': dinero_efectivo_total,
            # Orígenes
            'origen_pos': origen_pos,
            'origen_wa': origen_wa,
            'origen_del': origen_del,
            # Catálogos de filtros
            'customers': customers,
            'cashiers': cashiers,
            'categories': categories,
            'products': products,
            # Filtros seleccionados
            'selected_cliente': request.GET.get('cliente', ''),
            'selected_usuario': request.GET.get('usuario', ''),
            'selected_metodo': request.GET.get('metodo', ''),
            'selected_tipo': request.GET.get('tipo', ''),
            'selected_origen': request.GET.get('origen', ''),
            'selected_estado': request.GET.get('estado', ''),
            'selected_producto': request.GET.get('producto', ''),
            'selected_categoria': request.GET.get('categoria', ''),
            'search_q': request.GET.get('q', ''),
            # JSON para gráficos
            'chart_days_labels_json': json.dumps(chart_days_labels),
            'chart_days_values_json': json.dumps(chart_days_values),
            'top_products_labels_json': json.dumps(top_products_labels),
            'top_products_quantities_json': json.dumps(top_products_quantities),
        }
        return render(request, 'reports/sales_report.html', context)


class ProfitsReportView(LoginRequiredMixin, View):
    def get(self, request):
        today = timezone.localdate()
        date_from_str = request.GET.get('desde', today.replace(day=1).strftime('%Y-%m-%d'))
        date_to_str = request.GET.get('hasta', today.strftime('%Y-%m-%d'))

        items = SaleItem.objects.filter(
            sale__created_at__date__gte=date_from_str,
            sale__created_at__date__lte=date_to_str,
            sale__status=SaleStatus.COMPLETADA
        ).select_related('product', 'sale').order_by('-sale__created_at')

        return render(request, 'reports/profits_report.html', {
            'items': items,
            'date_from': date_from_str,
            'date_to': date_to_str,
        })


class ExportSalesCSVView(LoginRequiredMixin, View):
    def get(self, request):
        sales_qs, date_from_str, date_to_str = filter_sales_queryset(request)
        sales = sales_qs.order_by('-created_at')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="ventas_filtradas_{date_from_str}_al_{date_to_str}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Ticket', 'Fecha y Hora', 'Cliente', 'Cajero', 'Canal Origen', 
            'Método Pago', 'Tipo', 'Subtotal RD$', 'Descuento RD$', 'Total RD$', 'Estado', 'Productos'
        ])

        for s in sales:
            client_name = s.customer.name if s.customer else "Consumidor Final"
            tipo_op = "Crédito" if s.payment_method == PaymentMethodChoices.FIADO else "Contado"
            items_str = ", ".join([f"{it.quantity}x {it.product.name}" for it in s.items.all()])
            writer.writerow([
                s.ticket_number,
                s.created_at.strftime('%d/%m/%Y %H:%M'),
                client_name,
                s.cashier.username,
                s.get_origin_display() if hasattr(s, 'get_origin_display') else s.origin,
                s.get_payment_method_display(),
                tipo_op,
                f"{s.subtotal:.2f}",
                f"{s.discount:.2f}",
                f"{s.total:.2f}",
                s.get_status_display(),
                items_str
            ])

        return response


class ExportSalesExcelView(LoginRequiredMixin, View):
    def get(self, request):
        sales_qs, date_from_str, date_to_str = filter_sales_queryset(request)
        sales = sales_qs.order_by('-created_at')

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Ventas')

        # Formatos profesionales
        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#EA580C', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'
        })
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#0F172A'})
        subtitle_fmt = workbook.add_format({'italic': True, 'font_color': '#64748B'})
        money_fmt = workbook.add_format({'num_format': 'RD$ #,##0.00'})
        total_money_fmt = workbook.add_format({'bold': True, 'num_format': 'RD$ #,##0.00', 'bg_color': '#FEF3C7', 'border': 1})
        total_label_fmt = workbook.add_format({'bold': True, 'align': 'right', 'bg_color': '#FEF3C7', 'border': 1})

        # Título
        worksheet.write(0, 0, 'Reporte de Ventas - ColmadoPOS', title_fmt)
        worksheet.write(1, 0, f'Período: {date_from_str} al {date_to_str}', subtitle_fmt)

        headers = [
            'No. Ticket', 'Fecha y Hora', 'Cliente', 'Cajero', 'Canal / Origen',
            'Método Pago', 'Tipo', 'Subtotal', 'Descuento', 'Total (RD$)', 'Estado', 'Detalle de Productos'
        ]
        start_row = 3
        for col_num, header in enumerate(headers):
            worksheet.write(start_row, col_num, header, header_fmt)

        total_sum = Decimal('0.00')
        row_num = start_row + 1

        for s in sales:
            client_name = s.customer.name if s.customer else "Consumidor Final"
            tipo_op = "Crédito" if s.payment_method == PaymentMethodChoices.FIADO else "Contado"
            items_str = ", ".join([f"{it.quantity}x {it.product.name}" for it in s.items.all()])
            worksheet.write(row_num, 0, s.ticket_number)
            worksheet.write(row_num, 1, s.created_at.strftime('%d/%m/%Y %H:%M'))
            worksheet.write(row_num, 2, client_name)
            worksheet.write(row_num, 3, s.cashier.username)
            worksheet.write(row_num, 4, s.get_origin_display() if hasattr(s, 'get_origin_display') else s.origin)
            worksheet.write(row_num, 5, s.get_payment_method_display())
            worksheet.write(row_num, 6, tipo_op)
            worksheet.write(row_num, 7, float(s.subtotal), money_fmt)
            worksheet.write(row_num, 8, float(s.discount), money_fmt)
            worksheet.write(row_num, 9, float(s.total), money_fmt)
            worksheet.write(row_num, 10, s.get_status_display())
            worksheet.write(row_num, 11, items_str)

            if s.status == SaleStatus.COMPLETADA:
                total_sum += s.total
            row_num += 1

        # Fila de Totales
        worksheet.write(row_num, 8, 'TOTAL GENERAL:', total_label_fmt)
        worksheet.write(row_num, 9, float(total_sum), total_money_fmt)

        # Ancho de columnas
        worksheet.set_column('A:A', 22)
        worksheet.set_column('B:B', 18)
        worksheet.set_column('C:C', 26)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:G', 16)
        worksheet.set_column('H:J', 16)
        worksheet.set_column('K:K', 14)
        worksheet.set_column('L:L', 40)

        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="ventas_filtradas_{date_from_str}_al_{date_to_str}.xlsx"'
        return response
