import io
import base64
import xlsxwriter
from datetime import datetime

from odoo import models, fields, api


class ExportBillWizard(models.TransientModel):
    _name = 'bio.export.bill.wizard'
    _description = 'Export Bills to Excel'

    move_ids = fields.Many2many('account.move', string='Bills')

    def action_export_excel(self):
        self.ensure_one()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()

        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})

        headers = [
            'Vendor bill number', 'Date of receipt by buyer',
            'Vendor Bill date', 'Internal Reference',
            'Product name', 'PCS', 'UOM',
            'EUR/HUF', 'EUR', 'HUF', 'Exchange rate'
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        row = 1
        for move in self.move_ids:
            for line in move.invoice_line_ids:
                worksheet.write(row, 0, move.name)
                worksheet.write(row, 1, str(move.date_of_receipt_by_buyer or ''))
                worksheet.write(row, 2, str(move.invoice_date or ''))
                worksheet.write(row, 3, line.product_id.default_code or '')
                worksheet.write(row, 4, line.product_id.name or '')
                worksheet.write(row, 5, line.quantity)
                worksheet.write(row, 6, line.product_uom_id.name or '')
                worksheet.write(row, 7, line.debit/line.quantity if line.quantity != 0 and line.currency_id.name == 'EUR' else 0)  # EUR/HUF
                worksheet.write(row, 8, line.price_subtotal if line.currency_id.name == 'EUR' else 0)  # EUR
                worksheet.write(row, 9, line.price_subtotal if line.currency_id.name == 'HUF' else line.debit)  # HUF
                worksheet.write(row, 10, line.debit/line.price_subtotal if line.price_subtotal != 0 else 1) #'Exchange rate'
                row += 1

        workbook.close()
        output.seek(0)

        filename = f'bill_export_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
