import base64
import io
from datetime import datetime
from odoo import fields, models, _, api
from odoo.exceptions import UserError

# Try to import Excel parsing library
try:
    import xlrd
    from xlrd import xldate
except ImportError:
    xlrd = None


class MrpProductionSheduleImportWizard(models.TransientModel):
    _name = 'bio.mrp.production.schedule.import.wizard'
    _description = 'MRP Production Shedule Import Wizard'

    @api.model
    def _default_warehouse_id(self):
        return self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)

    manufacturing_period = fields.Selection([
        ('month', 'Monthly'),
        ('week', 'Weekly')], string="Manufacturing Period",
        default='month', required=True,
        help="Default value for the time ranges in Master Production Schedule report.")
    warehouse_id = fields.Many2one('stock.warehouse', 'Production Warehouse',
        required=True, default=lambda self: self._default_warehouse_id())
    company_id = fields.Many2one('res.company', 'Company',
        default=lambda self: self.env.company)
    excel_file = fields.Binary(string='Excel File', required=True)
    filename = fields.Char(string='Filename')
    line_ids = fields.One2many(
        comodel_name='bio.mrp.production.schedule.lines.import.wizard',
        inverse_name='bio_mrp_production_schedule_wizard_id', string='Lines' )

    # Excel column configuration (0-indexed, A=0, B=1, C=2, etc.)
    header_row_number = fields.Integer(
        string='Header Row Number',
        default=4,
        required=True,
        help='Row number where column headers are located (1 = first row, 2 = second row, etc.)')
    default_code_column = fields.Integer(
        string='Product Code Column',
        default=1,
        required=True,
        help='Column number for product default_code (A=0, B=1, C=2, etc.)')
    first_date_column = fields.Integer(
        string='First Date Column',
        default=7,
        required=True,
        help='Column number where dates start (A=0, B=1, C=2, etc.)')

    # Import options
    set_replenish_equal_forecast = fields.Boolean(
        string='Suggested Replenishment = Forecasted Demand',
        default=True,
        help='When importing the forecast plan, the suggested replenishment for raw materials '
             'will align with the forecasted plan, ignoring the existing stock.')

    @api.onchange('manufacturing_period')
    def _onchange_manufacturing_period(self):
        """Update column configuration based on manufacturing period"""
        # You can customize these defaults based on your Excel templates
        if self.manufacturing_period == 'month':
            # For monthly: typically B=code, H onwards=dates
            self.header_row_number = 4
            self.default_code_column = 1
            self.first_date_column = 7
        elif self.manufacturing_period == 'week':
            # For weekly: C=code, G onwards=dates
            self.header_row_number = 9
            self.default_code_column = 2
            self.first_date_column = 6


    def action_open_wizard(self):
        return {
            'name': _('Open MRP Production Shedule Import Wizard'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'bio.mrp.production.schedule.import.wizard',
            'target': 'new',
            'context': {},
        }

    def action_upload(self):
        """Parse Excel file and create wizard lines"""
        self.ensure_one()

        if not self.excel_file:
            raise UserError(_('Please upload an Excel file.'))

        if not xlrd:
            raise UserError(_('Python library "xlrd" is not installed. Please install it: pip install xlrd'))

        # Decode the file
        try:
            file_data = base64.b64decode(self.excel_file)
        except Exception as e:
            raise UserError(_('Error reading file: %s') % str(e))

        # Clear existing lines
        self.line_ids.unlink()

        # Parse Excel file using xlrd
        date_columns, lines_to_create = self._parse_excel_xlrd(file_data)

        # Create lines
        if lines_to_create:
            self.env['bio.mrp.production.schedule.lines.import.wizard'].create(lines_to_create)

        # Return view with lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bio.mrp.production.schedule.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _parse_excel_xlrd(self, file_data):
        """Parse Excel file using xlrd library (.xls format)"""
        try:
            workbook = xlrd.open_workbook(file_contents=file_data)
            sheet = workbook.sheet_by_index(0)
        except Exception as e:
            raise UserError(_('Error parsing Excel file with xlrd: %s') % str(e))

        # Convert header row number from 1-based to 0-based index
        header_row_idx = self.header_row_number - 1

        # Parse header row (dates)
        if sheet.nrows < header_row_idx + 1:
            raise UserError(_('Excel file does not have enough rows. Header row %d not found.') % self.header_row_number)

        header_row = sheet.row_values(header_row_idx)

        # Extract dates from header starting from configured column
        date_columns = []
        for col_idx in range(self.first_date_column-1, len(header_row)):
            cell_value = header_row[col_idx]
            if cell_value:
                try:
                    forecast_date = None
                    # Check if it's a date number (xlrd stores dates as float)
                    if isinstance(cell_value, float):
                        # Convert Excel date number to Python date
                        date_tuple = xldate.xldate_as_tuple(cell_value, workbook.datemode)
                        forecast_date = datetime(*date_tuple).date()
                    elif isinstance(cell_value, str):
                        # Try to parse date from DD.MM.YYYY format
                        forecast_date = datetime.strptime(cell_value.strip(), '%d.%m.%Y').date()

                    if forecast_date:
                        date_columns.append((col_idx, forecast_date))
                except (ValueError, xlrd.xldate.XLDateError):
                    # Skip invalid dates
                    continue

        if not date_columns:
            raise UserError(_('No valid dates found in header row %d starting from column %d. Expected format: DD.MM.YYYY (e.g., 01.12.2025)') % (self.header_row_number, self.first_date_column))

        # Parse data rows (starting from row after header)
        lines_to_create = []
        for row_idx in range(header_row_idx + 1, sheet.nrows):
            row = sheet.row_values(row_idx)

            # Get values from configured columns
            default_code = row[self.default_code_column-1] if self.default_code_column-1 < len(row) else None

            if not default_code:
                continue  # Skip empty rows

            if self.manufacturing_period == 'month' and not row[5]:
                continue

            if default_code == "vendor code":
                continue

            # Convert default_code to string
            if isinstance(default_code, float):
                default_code = str(int(default_code))
            else:
                default_code = str(default_code).strip()

            # Find product by default_code
            product = self.env['product.product'].search([('default_code', '=', default_code)], limit=1)

            # Create line for each date column
            for col_idx, forecast_date in date_columns:
                qty = row[col_idx] if col_idx < len(row) else 0

                # Skip if quantity is 0 or empty
                if not qty:
                    continue

                try:
                    forecast_qty = float(qty)
                except (ValueError, TypeError):
                    forecast_qty = 0.0

                if forecast_qty <= 0:
                    continue

                line_vals = {
                    'bio_mrp_production_schedule_wizard_id': self.id,
                    'default_code': default_code,
                    'forecast_date': forecast_date,
                    'forecast_qty': forecast_qty,
                }

                if product:
                    # Search for BOM - try multiple approaches to maximize compatibility
                    bom = False

                    # Approach 1: Most specific - with company and product variant
                    if self.warehouse_id.company_id:
                        bom = self.env['mrp.bom'].search([
                            ('product_tmpl_id', '=', product.product_tmpl_id.id),
                            '|', ('product_id', '=', product.id), ('product_id', '=', False),
                            ('type', '=', 'normal'),
                            '|', ('company_id', '=', self.warehouse_id.company_id.id), ('company_id', '=', False)
                        ], order='product_id DESC, company_id DESC', limit=1)

                    # Approach 2: Without company filter
                    if not bom:
                        bom = self.env['mrp.bom'].search([
                            ('product_tmpl_id', '=', product.product_tmpl_id.id),
                            '|', ('product_id', '=', product.id), ('product_id', '=', False),
                            ('type', '=', 'normal'),
                        ], order='product_id DESC', limit=1)

                    # Approach 3: Simplest - just by template and type (last resort)
                    if not bom:
                        bom = self.env['mrp.bom'].search([
                            ('product_tmpl_id', '=', product.product_tmpl_id.id),
                            ('type', '=', 'normal'),
                        ], limit=1)

                    if bom:
                        line_vals.update({
                            'product_id': product.id,
                            'bom_id': bom.id,
                            'state': 'ready_for_import',
                            'message': _('Product and BOM found'),
                        })
                    else:
                        # Count total BOMs for debugging
                        total_boms = self.env['mrp.bom'].search_count([
                            ('product_tmpl_id', '=', product.product_tmpl_id.id),
                        ])
                        line_vals.update({
                            'product_id': product.id,
                            'state': 'bill_not_found',
                            'message': _('BOM not found for product "%s" (template has %d BOMs total)') % (default_code, total_boms),
                        })
                else:
                    line_vals.update({
                        'state': 'product_not_found',
                        'message': _('Product with code "%s" not found in database') % default_code,
                    })
                lines_to_create.append(line_vals)

        return date_columns, lines_to_create

    def _set_replenish_equal_forecast_with_indirect_demand(self, production_schedules):
        """Set replenish_qty = forecast_qty + indirect_demand_qty for imported schedules

        For raw materials (components), the formula should account for indirect demand:
        - Normal formula: Suggested = Forecast + Indirect Demand - Stock
        - With this option: Suggested = Forecast + Indirect Demand (ignoring stock)

        Args:
            production_schedules: recordset of mrp.production.schedule
        """
        if not production_schedules:
            return

        # Get computed state with indirect_demand_qty values
        try:
            schedule_states = production_schedules.get_production_schedule_view_state()
        except Exception as e:
            raise UserError(_('Failed to compute production schedule state: %s') % str(e))

        # Build a mapping of schedule_id -> list of forecast_states
        schedule_forecast_states = {}
        for state in schedule_states:
            schedule_id = state['id']
            schedule_forecast_states[schedule_id] = state.get('forecast_ids', [])

        # Update replenish_qty for each forecast line
        updated_count = 0
        for prod_schedule in production_schedules:
            forecast_states = schedule_forecast_states.get(prod_schedule.id, [])

            # Get all forecast lines for this production schedule
            forecast_lines = prod_schedule.forecast_ids

            if not forecast_lines:
                continue

            # Group forecast lines by period for proportional distribution
            forecasts_by_period = {}
            for forecast in forecast_lines:
                # Find the period that contains this forecast.date
                matching_state = None
                for forecast_state in forecast_states:
                    date_start = forecast_state.get('date_start')
                    date_stop = forecast_state.get('date_stop')

                    # Check if forecast.date falls within this period
                    if date_start and date_stop:
                        if date_start <= forecast.date <= date_stop:
                            matching_state = forecast_state
                            break

                if matching_state:
                    period_key = (matching_state.get('date_start'), matching_state.get('date_stop'))
                    if period_key not in forecasts_by_period:
                        forecasts_by_period[period_key] = {
                            'forecasts': [],
                            'state': matching_state
                        }
                    forecasts_by_period[period_key]['forecasts'].append(forecast)

            # Update each forecast line with proportionally distributed indirect demand
            for period_key, period_data in forecasts_by_period.items():
                forecasts = period_data['forecasts']
                matching_state = period_data['state']

                # Get period totals from the computed state
                period_indirect_demand_qty = matching_state.get('indirect_demand_qty', 0.0)

                # Calculate total forecast_qty for this period to determine proportions
                total_period_forecast_qty = sum(f.forecast_qty for f in forecasts)

                for forecast in forecasts:
                    # Distribute indirect_demand proportionally based on forecast_qty
                    if total_period_forecast_qty > 0:
                        # Proportional distribution
                        proportion = forecast.forecast_qty / total_period_forecast_qty
                        forecast_indirect_demand = period_indirect_demand_qty * proportion
                    else:
                        # If no forecast_qty, distribute equally
                        forecast_indirect_demand = period_indirect_demand_qty / len(forecasts)

                    # Calculate: replenish = forecast + proportional indirect_demand
                    replenish_qty = forecast.forecast_qty + forecast_indirect_demand

                    forecast.write({
                        'replenish_qty': replenish_qty,
                        'replenish_qty_updated': True,
                    })
                    updated_count += 1

            # Handle forecasts that didn't match any period (fallback)
            all_processed = set()
            for period_data in forecasts_by_period.values():
                all_processed.update(period_data['forecasts'])

            unmatched_forecasts = set(forecast_lines) - all_processed
            for forecast in unmatched_forecasts:
                forecast.write({
                    'replenish_qty': forecast.forecast_qty,
                    'replenish_qty_updated': True,
                })
                updated_count += 1

    def action_import(self):
        """Import validated lines to mrp.production.schedule"""
        self.ensure_one()

        lines_to_import = self.line_ids.filtered(lambda l: l.state == 'ready_for_import')

        if not lines_to_import:
            raise UserError(_('No valid lines to import. Please upload and validate Excel file first.'))

        # Group lines by (product, BOM) to handle cases where BOM.product_id might be False
        lines_by_product_bom = {}
        for line in lines_to_import:
            key = (line.product_id, line.bom_id)
            if key not in lines_by_product_bom:
                lines_by_product_bom[key] = []
            lines_by_product_bom[key].append(line)

        production_schedule_model = self.env['mrp.production.schedule']
        forecast_model = self.env['mrp.product.forecast']

        imported_schedules = self.env['mrp.production.schedule']  # Empty recordset
        imported_forecasts_count = 0

        for (product, bom), lines in lines_by_product_bom.items():
            # Find or create production schedule using product from line (not from BOM)
            production_schedule = production_schedule_model.search([
                ('product_id', '=', product.id),
                ('bom_id', '=', bom.id),
                ('warehouse_id', '=', self.warehouse_id.id),
            ], limit=1)

            if not production_schedule:
                production_schedule = production_schedule_model.create({
                    'product_id': product.id,
                    'bom_id': bom.id,
                    'warehouse_id': self.warehouse_id.id,
                    'company_id': self.warehouse_id.company_id.id,
                })

            # Track all schedules (both new and existing)
            imported_schedules |= production_schedule

            # Create or update forecasts for each date
            for line in lines:
                # Find existing forecast for this date
                existing_forecast = forecast_model.search([
                    ('production_schedule_id', '=', production_schedule.id),
                    ('date', '=', line.forecast_date),
                ], limit=1)

                if existing_forecast:
                    # Update existing forecast
                    existing_forecast.write({
                        'forecast_qty': line.forecast_qty,
                    })
                else:
                    # Create new forecast
                    forecast_model.create({
                        'production_schedule_id': production_schedule.id,
                        'date': line.forecast_date,
                        'forecast_qty': line.forecast_qty,
                    })
                    imported_forecasts_count += 1

                # Mark line as imported
                line.write({'state': 'imported'})

        total_schedules = len(lines_by_product_bom)
        total_forecasts = len(lines_to_import)

        # Apply Suggested=Forecasted logic if checkbox is enabled
        if self.set_replenish_equal_forecast and imported_schedules:
            self._set_replenish_equal_forecast_with_indirect_demand(imported_schedules)

        # Commit changes to database
        self.env.cr.commit()

        message = _('Successfully imported:\n- %d production schedule(s)\n- %d forecast line(s)\n\nCheck Master Production Schedule to see results.') % (total_schedules, total_forecasts)

        # Close wizard and show notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Successful'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class MrpProductionSheduleLinessImportWizard(models.TransientModel):
    _name = 'bio.mrp.production.schedule.lines.import.wizard'
    _description = 'MRP Production Shedule Lines Import Wizard'
    _order = 'default_code, forecast_date'

    bio_mrp_production_schedule_wizard_id = fields.Many2one(
        comodel_name='bio.mrp.production.schedule.import.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade')
    company_id = fields.Many2one('res.company', 'Company',
        related='bio_mrp_production_schedule_wizard_id.company_id')
    # Product information
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        help='Product found by default_code')
    product_tmpl_id = fields.Many2one(
        'product.template',
        related='product_id.product_tmpl_id',
        readonly=True,
        store=False)
    bom_id = fields.Many2one(
        'mrp.bom', "Bill of Materials",
        domain="[('product_tmpl_id', '=', product_tmpl_id), '|', ('product_id', '=', product_id), ('product_id', '=', False)]",
        check_company=True)
    default_code = fields.Char(
        string='Product Code',
        required=True,
        help='Product code from Excel file')

    # Forecast data
    forecast_date = fields.Date(
        string='Forecast Date',
        required=True,
        help='Date from Excel header (DD.MM.YYYY format)')
    forecast_qty = fields.Float(
        string='Forecast Quantity',
        digits='Product Unit of Measure',
        required=True,
        help='Quantity from Excel cell')

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('product_not_found', 'Product Not Found'),
        ('bill_not_found', 'BOM Not Found'),
        ('ready_for_import', 'Ready For Import'),
        ('imported', 'Imported'),
        ('error', 'Error'),
    ], string='Status', default='draft', required=True)

    message = fields.Text(
        string='Message',
        help='Status message or error description')

