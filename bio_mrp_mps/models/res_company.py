from odoo import models


class Company(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        if len(vals) == 1:
            fname, = vals.keys()
            if fname == 'manufacturing_period' and self.env.user.has_group('mrp.group_mrp_manager'):
                return super(Company, self.sudo()).write(vals)
        return super().write(vals)
