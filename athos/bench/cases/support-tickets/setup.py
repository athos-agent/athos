"""The workspace: one day of fictitious support tickets in two languages, and the orders behind them.
The traps the method handles: a refund window counted from delivery (not from the order), shipping refunded only for
damaged items, an annual plan refunded by unused whole months, a chargeback threat that goes to the lead, a second
late delivery that earns a credit, a late order where no date may be promised, and a customer offering a card number."""
import sys
from pathlib import Path

TICKETS = """ticket_id,order_id,lang,message
T01,O101,en,"I want to return the desk lamp, I changed my mind. How do I get my money back?"
T02,O102,es,"Quiero devolver la silla, no me gustó. La compré hace más de un mes."
T03,O103,en,"The mug arrived broken. I want a full refund."
T04,O104,en,"Please cancel my annual plan and refund what I haven't used."
T05,O105,es,"Cancelen mi plan mensual y devuélvanme este mes."
T06,O106,en,"Refund me now or I will file a chargeback with my bank."
T07,O107,es,"Otra vez llegó tarde mi pedido. Es la segunda vez."
T08,O108,en,"Where is my order? When will it arrive?"
T09,O109,es,"Me cobraron dos veces. Les paso mi tarjeta 4111 1111 1111 1111 para que lo revisen."
"""
ORDERS = """order_id,customer,kind,item,order_date,delivery_date,item_price,shipping,status,late_deliveries_90d
O101,customer-a,product,desk lamp,2026-10-10,2026-10-14,40.00,6.00,delivered,0
O102,customer-b,product,chair,2026-09-20,2026-10-08,120.00,15.00,delivered,0
O103,customer-c,product,mug,2026-10-20,2026-10-24,18.00,5.00,delivered,0
O104,customer-d,annual_plan,annual plan,2026-07-01,,120.00,0.00,active,0
O105,customer-e,monthly_plan,monthly plan,2026-10-01,,15.00,0.00,active,0
O106,customer-f,product,headphones,2026-08-01,2026-08-05,80.00,7.00,delivered,0
O107,customer-g,product,backpack,2026-10-15,2026-10-29,60.00,8.00,delivered,1
O108,customer-h,product,keyboard,2026-10-20,,70.00,6.00,in_transit,0
O109,customer-i,product,notebook set,2026-10-25,2026-10-28,30.00,4.00,delivered,0
"""


def main(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "tickets.csv").write_text(TICKETS)
    (d / "orders.csv").write_text(ORDERS)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
