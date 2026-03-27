import base64
import xlrd
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil import tz


class PricelistImportWizard(models.TransientModel):
    _name = 'pricelist.import.wizard'
    _description = 'Pricelist Import Wizard'

    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True)
    start_date = fields.Datetime(string='Start Date', required=True)
    end_date = fields.Datetime(string='End Date')
    excel_file = fields.Binary(string='Excel File', required=True)
    filename = fields.Char(string='Filename')
    header_row = fields.Integer(string='Header Row', default=1)
    internal_ref_col = fields.Integer(string='Internal Reference Column', default=1)
    price_col = fields.Integer(string='Price Column', default=2)


    @api.onchange('start_date')
    def _onchange_date_start(self):
        if self.start_date:
            user_timezone = tz.gettz(self.env.context.get('tz')) or tz.tzutc()
            # user_timezone = tz.tzutc()
            new_date_start = self.start_date.astimezone(user_timezone)
            # Отримання зміщення для конкретного моменту часу
            offset = new_date_start.utcoffset()
            # Переведення зміщення в години
            offset_hours = offset.total_seconds() / 3600
            self.start_date = new_date_start.replace(hour=0, minute=0, second=0, microsecond=0,
                                                               tzinfo=None) - timedelta(hours=offset_hours)
            pass

    @api.onchange('end_date')
    def _onchange_date_end(self):
        if self.end_date:
            user_timezone = tz.gettz(self.env.context.get('tz')) or tz.tzutc()
            # user_timezone = tz.tzutc()
            new_date_end = self.end_date.astimezone(user_timezone)
            # Отримання зміщення для конкретного моменту часу
            offset = new_date_end.utcoffset()
            # Переведення зміщення в години
            offset_hours = offset.total_seconds() / 3600
            self.end_date = new_date_end.replace(hour=23, minute=59, second=59, microsecond=59,
                                                           tzinfo=None) - timedelta(hours=offset_hours)
            pass

    @api.constrains('excel_file', 'filename')
    def _check_file_format(self):
        for record in self:
            if record.filename and not record.filename.lower().endswith(('.xlsx', '.xls')):
                raise ValidationError(_('File must be in .xlsx or .xls format.'))

    def _parse_excel_file(self):
        """Parse Excel file and return data"""
        if not self.excel_file:
            raise UserError(_('Please select an Excel file.'))

        try:
            file_data = base64.b64decode(self.excel_file)
            workbook = xlrd.open_workbook(file_contents=file_data)
            worksheet = workbook.sheet_by_index(0)

            if self.header_row is None or self.internal_ref_col is None or self.price_col is None:
                raise UserError(
                    _('Required columns not found. Please ensure your Excel file contains "Internal Reference" and "Price" columns.'))

            # Parse data rows
            data_rows = []
            for row_idx in range(self.header_row, worksheet.nrows):
                try:
                    internal_ref = str(worksheet.cell_value(row_idx, self.internal_ref_col-1)).strip()
                    price_cell = worksheet.cell_value(row_idx, self.price_col-1)

                    if not internal_ref:
                        continue

                    # Convert price to float
                    if isinstance(price_cell, str):
                        price = float(price_cell.replace(',', '.')) if price_cell.strip() else 0.0
                    else:
                        price = float(price_cell) if price_cell else 0.0

                    data_rows.append({
                        'internal_reference': internal_ref,
                        'price': price,
                        'row_number': row_idx + 1
                    })
                except (ValueError, TypeError) as e:
                    # Skip invalid rows but continue processing
                    continue

            return data_rows

        except Exception as e:
            raise UserError(_('Error reading Excel file: %s') % str(e))

    def _find_products(self, internal_references):
        """Find products by internal reference"""
        products = self.env['product.template'].search([
            ('default_code', 'in', internal_references),
            ('active', '=', True)
        ])

        product_dict = {product.default_code: product for product in products}
        return product_dict

    def _process_pricelist_items(self, data_rows):
        """Process and update pricelist items"""
        if not data_rows:
            raise UserError(_('No valid data found in the Excel file.'))

        # Get all internal references
        internal_references = [row['internal_reference'] for row in data_rows]
        product_dict = self._find_products(internal_references)

        created_count = 0
        updated_count = 0
        skipped_count = 0

        # # Якщо треба зберегти в UTC назад (для створення записів)
        start_date = fields.Datetime.to_string(self.start_date)
        end_date = fields.Datetime.to_string(self.end_date)

        for row in data_rows:
            internal_ref = row['internal_reference']
            new_price = row['price']

            # Find product
            product = product_dict.get(internal_ref)
            if not product:
                skipped_count += 1
                continue

            # Check if pricelist item already exists
            existing_item = self.env['product.pricelist.item'].search([
                ('pricelist_id', '=', self.pricelist_id.id),
                ('product_tmpl_id', '=', product.id),
                ('date_start', '=', start_date),
                ('date_end', '=', end_date),
            ], limit=1)

            if existing_item:
                # Update existing item
                existing_item.write({
                    'fixed_price': new_price,
                })
                updated_count += 1
            else:
                # Create new item
                self.env['product.pricelist.item'].create({
                    'applied_on': '1_product',
                    'base': 'list_price',
                    'compute_price': 'fixed',
                    'company_id': self.pricelist_id.company_id.id or False,
                    'currency_id': self.pricelist_id.currency_id.id or False,
                    'pricelist_id': self.pricelist_id.id,
                    'product_tmpl_id': product.id,
                    'fixed_price': new_price,
                    'date_start': start_date,
                    'date_end': end_date,
                })
                created_count += 1

        return {
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count
        }

    def action_import(self):
        """Execute the import process"""
        self.ensure_one()

        try:
            # Parse Excel file
            data_rows = self._parse_excel_file()

            # Process pricelist items
            result = self._process_pricelist_items(data_rows)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import Successful'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            raise UserError(_('Import failed: %s') % str(e))

