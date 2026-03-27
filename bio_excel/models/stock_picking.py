# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from io import BytesIO
import xlsxwriter
import zipfile


class StockPicking(models.Model):
    _inherit = 'stock.picking'


    def _headers_biosfera_polska_export_xls(self):
        return [
            'firma',  # 0
            'typ dokumentu',  # 1
            'numer dokumentu',  # 2
            'typ dokumentu erp',  # 3
            'numer dokumentu erp',  # 4
            'data utworzenia',  # 5
            'data realizacji',  # 6
            'opis dokumentu',  # 7
            'magazyn',  # 8
            'magazyn docelowy',  # 9
            'kod kontrahenta',  # 10
            'l.p.adresu kontrahenta',  # 11
            'operator',  # 12
            'status',  # 13
            'stan',  # 14
            'typ dokumentu źródłowego',  # 15
            'numer dokumentu źródłowego',  # 16
            'l.p. pozycji',  # 17
            'kod towaru',  # 18
            'kod jl',  # 19
            'ilość do realizacji',  # 20
            'lokalizacja',  # 21
            'ilość zrealizowana',  # 22
            'cecha0',  # 23
            'cecha1',  # 24
            'cecha2',  # 25
            'cecha3',  # 26
            'cecha4',  # 27
            'cecha5',  # 28
            'cecha6',  # 29
            'cecha7',  # 30
            'cecha8',  # 31
            'cecha9',  # 32
            'cecha10',  # 33
            'cecha11',  # 34
            'cecha12',  # 35
            'cecha13',  # 36
            'cecha14',  # 37
            'cecha15',  # 38
            'cecha16',  # 39
            'cecha17',  # 40
            'cecha18',  # 41
            'cecha19',  # 42
            'przelicznik',  # 43
            'kod przelicznika',  # 44
            'lp dokumentu źródłowego',  # 45
            'atrybut #1',  # 46
            'atrybut #2',  # 47
            'atrybut #3',  # 48
            'atrybut #4',  # 49
            'atrybut #5',  # 50
        ]

    def _kod_towaru__biosfera_polska_export_xls(self, move):
        if not move.product_id:
            return ""

        vendor_code = move.product_id.seller_ids.filtered(
            lambda r: r.company_id.id == 6 and r.product_code
        )[:1]

        return vendor_code.product_code if vendor_code else move.product_id.default_code

    def action_biosfera_polska_export_xls(self):
        if not self:
            raise UserError(_('No document selected'))

        # Створюємо ZIP архів
        zip_output = BytesIO()

        format_green = {'bold': True, 'align': 'left', 'valign': 'vcenter', 'bg_color': '#C6EFCE'}
        format_yellow = {'bold': True, 'align': 'left', 'valign': 'vcenter', 'bg_color': '#FFEB9C'}
        headers = self._headers_biosfera_polska_export_xls()
        yellow_cell = (0, 3, 4, 8, 10, 17, 18, 20)

        with zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for picking in self:
                # Створюємо Excel для кожного picking
                output = BytesIO()
                workbook = xlsxwriter.Workbook(output, {'in_memory': True})
                header_format_green = workbook.add_format(format_green)
                header_format_yellow = workbook.add_format(format_yellow)
                worksheet = workbook.add_worksheet('dokumenty_import')
                worksheet.set_column(0, len(headers) - 1, 30.13)

                for col, header in enumerate(headers):
                    if col in yellow_cell:
                        worksheet.write(0, col, header, header_format_yellow)
                    else:
                        worksheet.write(0, col, header, header_format_green)

                # Записуємо назви товарів
                row = 1
                for move in picking.move_ids_without_package:
                    worksheet.write(row, 0, "Biosfera")
                    if picking.picking_type_code == 'incoming':
                        worksheet.write(row, 3, "PPM")
                    elif picking.picking_type_code == 'outgoing':
                        worksheet.write(row, 3, "PWM")
                    # worksheet.write(row, 4, picking.name)
                    if picking.purchase_id:
                        worksheet.write(row, 4, picking.purchase_id.origin or "")
                    elif picking.sale_id:
                        worksheet.write(row, 4, picking.sale_id.client_order_ref or "")
                    worksheet.write(row, 8, "magazyn pruszków")
                    # worksheet.write(row, 10, picking.partner_id.name if picking.partner_id else "")
                    worksheet.write(row, 10, "Biosfera")
                    worksheet.write(row, 17, row)
                    worksheet.write(row, 18, self._kod_towaru__biosfera_polska_export_xls(move))
                    worksheet.write(row, 20, self._get_product_qty_in_box(move))

                    row += 1

                workbook.close()
                output.seek(0)

                # Назва файлу
                date_str = picking.scheduled_date.strftime('%d-%m-%Y') if picking.scheduled_date else ''
                filename = f'{picking.name.replace("/", "-")}_{date_str}.xlsx'

                # Додаємо до ZIP
                zip_file.writestr(filename, output.getvalue())

        zip_output.seek(0)

        # Створюємо attachment для ZIP
        attachment = self.env['ir.attachment'].create({
            'name': f'transfers_export_{fields.Date.today().strftime("%d-%m-%Y")}.zip',
            'datas': base64.b64encode(zip_output.getvalue()),
            'mimetype': 'application/zip'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _get_product_qty_in_box(self, move):
        if not move.product_id:
            return 0

        if move.product_packaging_id and move.product_packaging_id.name.upper() == 'BOX':
            return move.quantity_done / move.product_packaging_id.qty

        for packing in move.product_id.packaging_ids:
            if packing.name and packing.name.upper() == 'BOX' and packing.qty:
                return move.quantity_done / packing.qty

        return 0
