/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { MrpMpsControlPanel } from "@mrp_mps/search/mrp_mps_control_panel";

// Register Dropdown components for the template
MrpMpsControlPanel.components = {
    ...MrpMpsControlPanel.components,
    Dropdown,
    DropdownItem,
};

// Patch the control panel to add Import from Excel handler and Time Range selector
patch(MrpMpsControlPanel.prototype, 'bio_mrp_mps.MrpMpsControlPanel', {
    /**
     * Get current manufacturing period from model data
     */
    get manufacturingPeriod() {
        return this.env.model.data && this.env.model.data.manufacturing_period || 'month';
    },

    /**
     * Change manufacturing period on the company and reload MPS
     * @private
     * @param {String} period - 'month', 'week', or 'day'
     */
    _onSetManufacturingPeriod(period) {
        if (this.manufacturingPeriod !== period) {
            this.env.model._saveCompanySettings({ manufacturing_period: period });
        }
    },

    /**
     * Handle click on "Import from Excel" button
     * @private
     */
    _onClickImportExcel(ev) {
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
     * Add Product Demand export and Suggested=Forecasted to Action menu items
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
            const selectedIds = Array.from(this.model.selectedRecords);

            if (selectedIds.length === 0) {
                notification.add(
                    _t('Please select at least one production schedule to export.'),
                    { type: 'warning' }
                );
                return;
            }

            const context = this.props.context || {};

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
            const selectedIds = Array.from(this.model.selectedRecords);

            if (selectedIds.length === 0) {
                notification.add(
                    _t('Please select at least one production schedule.'),
                    { type: 'warning' }
                );
                return;
            }

            const context = this.props.context || {};

            await orm.call(
                'mrp.production.schedule',
                'action_set_replenish_equal_forecast',
                [selectedIds],
                { context: context }
            );

            notification.add(
                _t('Suggested Replenishment has been set equal to Forecast Demand for all periods.'),
                { type: 'success' }
            );

            await this.env.model.load();

        } catch (error) {
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
