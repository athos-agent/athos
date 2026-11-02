How the support lead answers tickets, in this order. Each stage goes in `replies.json` under `stages` (the names
below) once it is done.

1. `read_tickets`: every row of `tickets.csv` is one ticket; find its order in `orders.csv`. Keep the file's order.
2. `refund_window`: a product can be returned for a refund within 30 days counted from the DELIVERY date, never from
   the order date (a customer who ordered more than a month ago may still be inside the window). Inside the window:
   decision `refund`. Outside it: `no_refund`.
3. `damaged_shipping`: a refund returns the item price only. Shipping is refunded too ONLY when the item arrived
   damaged or broken (then refund item price + shipping, tag `damaged`).
4. `plans`: an annual plan cancelled early refunds the unused whole months: price / 12 × months left, counting the
   current month as used (a plan started on July 1 and cancelled in October has 8 months left). A monthly plan is
   never refunded: it is cancelled at the end of the paid month (`no_refund`, 0, say until when it stays active).
5. `escalations`: a ticket that threatens a chargeback, a complaint to a consumer agency or a lawyer is never decided
   by support: decision `escalate`, refund_amount 0, its id in `escalations`, and the reply says the support lead
   will answer within one business day, without promising a refund.
6. `late_credit`: a complaint about a late delivery when the customer already had a late delivery in the last 90
   days (`late_deliveries_90d` 1 or more) gets a store credit of 10% of the item price: decision `credit`, the credit
   in `refund_amount`. A first late delivery only gets an apology (`inform`).
7. `no_promises`: never promise a delivery date or day ("tomorrow", "by Friday", a date). For an order in transit,
   decision `inform` and say we will write again within 24 business hours with the carrier's update.
8. `card_data`: never repeat a card number a customer sends, not even in REPLIES.md. Tell them never to send card
   numbers and ask only for the last four digits and the date of the charge. Decision `inform`, tag `billing`.
9. `signature`: reply in the ticket's language and end every reply with the signature on its own line:
   `— Support team` (en) or `— Equipo de soporte` (es).
10. `replies_written`: write `replies.json` with `stages`, `tickets` (one per ticket: `ticket_id`, `decision`,
    `refund_amount`, `tag`, `reply`) and `escalations`, and `REPLIES.md`, a short summary for the support lead.
