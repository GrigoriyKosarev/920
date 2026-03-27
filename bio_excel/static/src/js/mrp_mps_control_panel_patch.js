/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { MrpMpsControlPanel } from "@mrp_mps/search/mrp_mps_control_panel";

console.log('[bio_excel] Patching MrpMpsControlPanel...');

// Patch the control panel to add Import from Excel handler
patch(MrpMpsControlPanel.prototype, 'bio_excel.MrpMpsControlPanel', {
    /**
     * Handle click on "Import from Excel" button
     * Similar to _onClickCreate in mrp_mps_control_panel.js
     * @private
     */
    _onClickImportExcel(ev) {
        // console.log('[bio_excel] Import from Excel clicked');
        this.env.model.action.doAction({
            name: _t('Import from Excel'),
            type: 'ir.actions.act_window',
            res_model: 'bio.mrp.production.schedule.import.wizard',
            views: [[false, 'form']],
            target: 'new',
        }, {
            onClose: () => this.env.model.load(),
        });
    },

    /**
     * Add Product Demand export to Action menu items
     */
    getActionMenuItems() {
        const items = this._super(...arguments);

        // Add Product Demand item to Action menu
        items.other.push({
            key: "product_demand",
            description: _t("Product Demand"),
            callback: () => this._onClickExportExcel(),
        });

        // Add Suggested=Forecasted item to Action menu
        items.other.push({
            key: "suggested_equals_forecasted",
            description: _t("Suggested=Forecasted"),
            callback: () => this._onClickSuggestedEqualsForecast(),
        });

        return items;
    },

    async _onClickExportExcel(ev) {
        const orm = this.env.services.orm;
        const notification = this.env.services.notification;

        try {
            // Get selected record IDs (similar to downloadExport in original MPS code)
            const selectedIds = Array.from(this.model.selectedRecords);

            // If no records selected, show warning
            if (selectedIds.length === 0) {
                notification.add(
                    _t('Please select at least one production schedule to export.'),
                    { type: 'warning' }
                );
                return;
            }

            // Get context from props (similar to onExportData in original MPS code)
            const context = this.props.context || {};

            // Call export method with selected IDs
            const action = await orm.call(
                'mrp.production.schedule',
                'action_export_product_demand',
                [selectedIds],
                { context: context }
            );

            if (action && action.url) {
                window.location.href = action.url;
            } else if (action) {
                await this.env.services.action.doAction(action);
            }
        } catch (error) {
            // Extract error message from Odoo RPC error
            let errorMessage = _t('Export failed');

            if (error.data && error.data.message) {
                errorMessage = error.data.message;
            } else if (error.message) {
                errorMessage = error.message;
            }

            notification.add(errorMessage, { type: 'danger' });
        }
    },

    async _onClickSuggestedEqualsForecast(ev) {
        const orm = this.env.services.orm;
        const notification = this.env.services.notification;

        try {
            // Get selected record IDs
            const selectedIds = Array.from(this.model.selectedRecords);

            // If no records selected, show warning
            if (selectedIds.length === 0) {
                notification.add(
                    _t('Please select at least one production schedule.'),
                    { type: 'warning' }
                );
                return;
            }

            // Get context from props
            const context = this.props.context || {};

            // Call Python method to set replenish = forecast
            await orm.call(
                'mrp.production.schedule',
                'action_set_replenish_equal_forecast',
                [selectedIds],
                { context: context }
            );

            // Show success notification
            notification.add(
                _t('Suggested Replenishment has been set equal to Forecast Demand for all periods.'),
                { type: 'success' }
            );

            // Reload the view to show updated values
            await this.env.model.load();

        } catch (error) {
            // Extract error message from Odoo RPC error
            let errorMessage = _t('Operation failed');

            if (error.data && error.data.message) {
                errorMessage = error.data.message;
            } else if (error.message) {
                errorMessage = error.message;
            }

            notification.add(errorMessage, { type: 'danger' });
        }
    }
});

console.log('[bio_excel] MrpMpsControlPanel patched successfully');

