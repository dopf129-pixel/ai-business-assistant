# Guided seller cost onboarding

After Ozon and tax setup, Telegram now explicitly explains that Period Profit needs seller cost and offers a one-tap `Указать себестоимость` action with a `Сделать позже` escape hatch.

The cost screen shows coverage (`configured / total / missing`) and prioritizes products with no current seller cost. The seller selects a product and sends only a numeric RUB amount; after saving, Telegram immediately offers the next missing product.

For a product that has never had seller-confirmed cost, the first switch is effective today. Later changes retain the existing safety rule and start tomorrow so already-calculated current-day accruals are not silently re-costed.

This flow does not invent historical cost before the seller-confirmed effective date. Historical Period Profit still requires evidence for the requested past dates.
