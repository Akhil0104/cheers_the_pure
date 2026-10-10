# DispatchAI Demo Script

## Live evaluation flow (about 2 minutes)

### Step 1 — Open the B2B dashboard

- Log in as the demo B2B distributor account.
- Open the B2B dashboard.
- Explain that this shows the live distributor context for the account, including company and buyer information.

### Step 2 — Show the distributor and business context

- Point to the customer summary and current profile section.
- Explain that the dashboard is grounded in the business database, not just chat memory.
- Mention that this data is customer-specific and only the authenticated distributor can see it.

### Step 3 — Open DispatchAI

- Click the DispatchAI panel on the B2B dashboard.
- Tell the evaluator that the AI is connected to both business data and Hindsight memory.

### Step 4 — Session 1: customer provides important delivery preference

What to type:

> We usually need delivery after 4 PM because our shop is busy before that.

What the agent should return:

- confirmation that it understands the delivery preference
- acknowledgement of the operational requirement
- a response that suggests the constraint is now remembered

Technical feature demonstrated:

- Hindsight retain from the first session

What to explain:

- This is the first time the customer has said they prefer delivery after 4 PM.
- The system stores this as persistent business context, not as a raw database record.

### Step 5 — Show Hindsight retains the useful memory

- In the evaluation panel, point to the memory summary.
- Explain that the preference is stored in Hindsight under the buyer namespace.

### Step 6 — Start a completely new session

- Click the new session action in the demo panel.
- Explain that the previous memory remains available even though the session is new.

### Step 7 — Customer makes a new order request

What to type:

> I need 150 cases this time.

What the agent should return:

- a response that references the earlier delivery timing preference
- a grounded business answer that includes the relevant delivery constraint

Technical feature demonstrated:

- Hindsight recall across sessions

What to explain:

- The customer did not have to repeat the delivery rule manually.
- The AI uses stored context without inventing a new preference.

### Step 8 — Show the memory-used indicator

- Point to the status indicator showing Memory Used: Yes.
- Explain that this is not simply a casual chat; the response is using remembered business context.

### Step 9 — Demonstrate an unsupported discount request

What to type:

> Apply the 10% discount on 500ML you promised last time.

What the agent should return:

- it should not invent a discount
- it should check business records and Hindsight
- it should explain that no verified discount exists
- it should offer current verified pricing instead

Technical feature demonstrated:

- hallucination prevention
- business-data grounding
- refusal to invent unsupported promises

What to explain:

- The agent does not blindly trust a prior memory when a discount has not been officially recorded.
- It checks authoritative data before answering.

### Scenario overview

Scenario 1: Persistent delivery preference
- Problem: delivery timing is context that can be forgotten in a new session.
- Memory created: Yes
- Memory recalled: Yes
- Business data used: Yes
- Final result: customer preference is respected across interactions.

Scenario 2: Recurring order context
- Problem: a repeat order may omit prior constraints or patterns.
- Memory created: Yes
- Memory recalled: Yes
- Business data used: Yes
- Final result: the agent responds using both memory and order context.

Scenario 3: Unsupported discount / hallucination prevention
- Problem: the customer requests an unverified discount.
- Memory created: No new unsupported memory
- Memory recalled: Yes/No depending on prior history, but not trusted blindly
- Business data used: Yes
- Final result: no invented discount; current pricing provided instead

## Presenter guidance

Keep the explanation simple:

- This is not a generic chatbot.
- It remembers real business context for the right customer.
- It checks the database before answering.
- It refuses to invent discounts or commitments.
- It keeps customer memory isolated and secure.
