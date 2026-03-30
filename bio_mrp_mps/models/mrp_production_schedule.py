import base64
import logging
from io import BytesIO
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import xlsxwriter

_logger = logging.getLogger(__name__)


class MrpProductionSchedule(models.Model):
    _inherit = 'mrp.production.schedule'

    # ODOO-902
    max_to_replenish_qty = fields.Float(
        'Maximum to Replenish',
        default=99999,
        help="The maximum replenishment you would like to launch for each period in the MPS. Note that if the demand is higher than that amount, the remaining quantity will be transferred to the next period automatically."
    )
    excel_file = fields.Binary('Excel File', readonly=True)
    excel_filename = fields.Char('Filename', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        # mps = super().create(vals_list)

        existing_mps = []
        for i, vals in enumerate(vals_list):
            # Allow to add components of a BoM for MPS already created
            if vals.get('bom_id'):
                mps = self.search([
                    ('product_id', '=', vals['product_id']),
                    ('warehouse_id', '=', vals.get('warehouse_id', self._default_warehouse_id().id)),
                    ('company_id', '=', vals.get('company_id', self.env.company.id)),
                ], limit=1)
                if mps:
                    mps.bom_id = vals.get('bom_id')
                    existing_mps.append((i, mps.id))

        for i_remove, __ in reversed(existing_mps):
            del vals_list[i_remove]

        mps = super().create(vals_list)

        mps_ids = mps.ids
        for i, mps_id in existing_mps:
            mps_ids.insert(i, mps_id)
        mps = self.browse(mps_ids)

        components_list = set()
        components_vals = []
        for record in mps:
            bom = record.bom_id
            if not bom:
                continue
            dummy, components = bom.explode(record.product_id, 1)
            for component in components:
                if component[0].product_id.type != 'consu':
                    components_list.add((component[0].product_id.id, record.warehouse_id.id, record.company_id.id))
        for component in components_list:
            if self.env['mrp.production.schedule'].search([
                ('product_id', '=', component[0]),
                ('warehouse_id', '=', component[1]),
                ('company_id', '=', component[2]),
            ], limit=1):
                continue
            components_vals.append({
                'product_id': component[0],
                'warehouse_id': component[1],
                'company_id': component[2]
            })
        if components_vals:
            self.env['mrp.production.schedule'].create(components_vals)
        return mps

    @api.model
    def action_export_product_demand(self, ids=None):
        """Export Product Demand data to Excel

        Args:
            ids: List of production schedule IDs to export
        """
        _logger.info('Product Demand export called with IDs: %s', ids)

        if not xlsxwriter:
            raise UserError(_('Please install xlsxwriter python library to use this feature.\n'
                            'Command: pip install xlsxwriter'))

        # Get production schedules - use provided IDs or all if empty
        if ids:
            production_schedule_ids = self.browse(ids)
        else:
            production_schedule_ids = self.search([])

        _logger.info('Found %d production schedule(s) to export', len(production_schedule_ids))

        if not production_schedule_ids:
            raise UserError(_('No production schedules found to export.'))

        # Get computed state with indirect_demand_qty values
        try:
            production_schedule_states = production_schedule_ids.get_production_schedule_view_state()
        except Exception as e:
            raise UserError(_('Failed to compute production schedule state: %s') % str(e))

        # Collect all dates from forecast_ids in states
        all_dates = set()
        schedule_data = {}  # Store computed data by schedule id
        has_any_data = False

        for state in production_schedule_states:
            schedule_id = state['id']
            schedule_data[schedule_id] = {
                'product_id': state['product_id'],
                'forecast_by_date': {}
            }

            for forecast in state.get('forecast_ids', []):
                date_start = forecast.get('date_start')
                indirect_demand_qty = forecast.get('indirect_demand_qty', 0.0)

                if date_start and indirect_demand_qty != 0.0:
                    all_dates.add(date_start)
                    schedule_data[schedule_id]['forecast_by_date'][date_start] = indirect_demand_qty
                    has_any_data = True

        # Check if we have any data to export BEFORE creating workbook
        if not has_any_data or not all_dates:
            _logger.warning('No indirect demand data found for selected production schedules (IDs: %s)', ids)
            raise UserError(_('No data to export. Selected production schedules have no Indirect Demand Forecast values.'))

        # Sort dates
        sorted_dates = sorted(list(all_dates))

        # Create Excel file in memory
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Product Demand')

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D3D3D3',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        data_format = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        number_format = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'num_format': '#,##0.00'
        })

        date_format = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'num_format': 'dd.mm.yyyy'
        })

        # Write header row
        col = 0
        worksheet.write(0, col, 'Product Internal Reference', header_format)
        col += 1
        worksheet.write(0, col, 'Product Name', header_format)
        col += 1

        # Write period date headers
        for date in sorted_dates:
            worksheet.write(0, col, date, date_format)
            col += 1

        # Add Total column
        worksheet.write(0, col, 'Total', header_format)
        total_col = col

        # Set column widths
        worksheet.set_column(0, 0, 20)  # Product Internal Reference
        worksheet.set_column(1, 1, 30)  # Product Name
        worksheet.set_column(2, total_col, 12)  # Date columns and Total

        # Write data rows - one row per production schedule
        row = 1

        for prod_schedule in production_schedule_ids:
            schedule_id = prod_schedule.id

            # Skip if no data computed for this schedule
            if schedule_id not in schedule_data:
                continue

            product = prod_schedule.product_id
            forecast_by_date = schedule_data[schedule_id]['forecast_by_date']

            # Skip if has_indirect_demand is False (no indirect demand)
            # Check if there's any non-zero indirect demand
            has_demand = any(qty != 0.0 for qty in forecast_by_date.values())
            if not has_demand:
                continue

            # Write product info
            col = 0
            worksheet.write(row, col, product.default_code or '', data_format)
            col += 1
            worksheet.write(row, col, product.name or '', data_format)
            col += 1

            # Write indirect demand quantities for each period
            total_indirect_demand = 0.0
            for date in sorted_dates:
                indirect_demand_qty = forecast_by_date.get(date, 0.0)
                worksheet.write(row, col, indirect_demand_qty, number_format)
                total_indirect_demand += indirect_demand_qty
                col += 1

            # Write total
            worksheet.write(row, total_col, total_indirect_demand, number_format)
            row += 1

        # Close workbook and get file data
        workbook.close()
        output.seek(0)
        file_data = output.read()
        output.close()

        # Encode file to base64
        excel_file = base64.b64encode(file_data)

        # Create attachment for download
        filename = 'production_schedule_export.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': excel_file,
            'res_model': 'mrp.production.schedule',
            'res_id': 0,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Return action to download file
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    @api.model
    def action_set_replenish_equal_forecast(self, ids=None):
        """Set Suggested Replenishment equal to Forecast Demand for all periods.

        Entry point for JS Action menu. Delegates to _set_replenish_equal_forecast().

        Args:
            ids: List of production schedule IDs
        """
        if not ids:
            raise UserError(_('No production schedules selected.'))

        production_schedules = self.browse(ids)
        if not production_schedules:
            raise UserError(_('No production schedules found.'))

        production_schedules._set_replenish_equal_forecast()
        self.env.cr.commit()
        return True

    def _set_replenish_equal_forecast(self):
        """Set replenish_qty = forecast_qty + indirect_demand_qty for all periods.

        Works on the current recordset. Ignores current inventory levels.
        For components with indirect demand, distributes it proportionally
        across forecast lines within each period.
        """
        if not self:
            return

        _logger.info('Suggested=Forecasted called for IDs: %s', self.ids)

        try:
            schedule_states = self.get_production_schedule_view_state()
        except Exception as e:
            raise UserError(_('Failed to compute production schedule state: %s') % str(e))

        # Build a mapping of schedule_id -> list of forecast_states
        schedule_forecast_states = {}
        for state in schedule_states:
            schedule_forecast_states[state['id']] = state.get('forecast_ids', [])

        total_forecasts_updated = 0

        for prod_schedule in self:
            forecast_states = schedule_forecast_states.get(prod_schedule.id, [])
            forecast_lines = prod_schedule.forecast_ids

            if not forecast_lines:
                _logger.warning('Production schedule %s has no forecast lines', prod_schedule.id)
                continue

            # Group forecast lines by period for proportional distribution
            forecasts_by_period = {}
            for forecast in forecast_lines:
                matching_state = None
                for forecast_state in forecast_states:
                    date_start = forecast_state.get('date_start')
                    date_stop = forecast_state.get('date_stop')
                    if date_start and date_stop and date_start <= forecast.date <= date_stop:
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
                period_indirect_demand_qty = period_data['state'].get('indirect_demand_qty', 0.0)
                total_period_forecast_qty = sum(f.forecast_qty for f in forecasts)

                for forecast in forecasts:
                    if total_period_forecast_qty > 0:
                        proportion = forecast.forecast_qty / total_period_forecast_qty
                        forecast_indirect_demand = period_indirect_demand_qty * proportion
                    else:
                        forecast_indirect_demand = period_indirect_demand_qty / len(forecasts)

                    replenish_qty = forecast.forecast_qty + forecast_indirect_demand
                    forecast.write({
                        'replenish_qty': replenish_qty,
                        'replenish_qty_updated': True,
                    })
                    total_forecasts_updated += 1

            # Handle forecasts that didn't match any period (fallback)
            all_processed = set()
            for period_data in forecasts_by_period.values():
                all_processed.update(period_data['forecasts'])

            unmatched_forecasts = set(forecast_lines) - all_processed
            for forecast in unmatched_forecasts:
                _logger.warning('Forecast date=%s did not match any period, using forecast_qty only', forecast.date)
                forecast.write({
                    'replenish_qty': forecast.forecast_qty,
                    'replenish_qty_updated': True,
                })
                total_forecasts_updated += 1

        _logger.info('Updated %d forecast line(s) for %d production schedule(s)',
                    total_forecasts_updated, len(self))

