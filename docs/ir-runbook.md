# Incident Response Runbook: Account Takeover and Payments Fraud

Scope: suspected account takeover (ATO) leading to fraudulent
cross-border transfers. This is a lab runbook: concrete enough to
practice with, generic enough to adapt to a real team.

Severity guidance: one confirmed ATO with money movement is at least
SEV-2. Multiple accounts or an active cash-out in progress is SEV-1.

## 1. Detect

Signals that start this runbook:

- Fraud engine `block` decisions spiking for one sender or one payee.
- Impossible-travel findings paired with new-device findings.
- Customer report: "I did not send this transfer."
- Login anomaly: password reset followed within minutes by a new payee
  and a transfer above the usual amount.

Example queries (adapt table and field names to your warehouse):

```sql
-- Senders with stacked high-severity findings in the last hour
SELECT sender_id, COUNT(*) AS blocks
FROM fraud_findings
WHERE decided_at > NOW() - INTERVAL '1 hour'
  AND decision = 'block'
GROUP BY sender_id
HAVING COUNT(*) >= 2
ORDER BY blocks DESC;
```

```sql
-- New payee followed by a large transfer within 24h
SELECT t.sender_id, t.payee_id, t.amount, t.decided_at
FROM transfers t
JOIN payees p ON p.payee_id = t.payee_id AND p.sender_id = t.sender_id
WHERE t.decided_at > NOW() - INTERVAL '24 hours'
  AND p.created_at > t.decided_at - INTERVAL '24 hours'
  AND t.amount >= 500
ORDER BY t.amount DESC;
```

```sql
-- Password reset then transfer in under 30 minutes
SELECT a.sender_id, a.reset_at, t.tx_id, t.amount, t.decided_at
FROM auth_events a
JOIN transfers t ON t.sender_id = a.sender_id
WHERE a.event = 'password_reset'
  AND t.decided_at BETWEEN a.reset_at AND a.reset_at + INTERVAL '30 minutes';
```

Triage checklist:

- [ ] Confirm the transfer is genuinely unauthorized (contact the customer
      through a verified channel, never the phone number on the account
      if it may have been changed).
- [ ] Pull the full session history: logins, device fingerprints, IP
      geolocation, password or email changes in the last 7 days.
- [ ] List every payee added in the last 7 days and every transfer to them.
- [ ] Check whether the same device fingerprint, IP, or payee touches
      other accounts (campaign indicator).

## 2. Contain

- [ ] Force logout of all sessions for the affected sender and lock the
      account to outbound transfers (allow inbound only if the product
      supports it).
- [ ] Require password reset plus fresh MFA enrollment before unlock.
- [ ] Hold or recall in-flight transfers to the suspect payee. Record
      which rail each transfer is on and the recall window for that rail.
- [ ] Blocklist the attacker device fingerprint and IP at the edge.
- [ ] If a campaign is indicated, apply the same holds to the full set
      of affected senders before notifying each one.

Do not tip off the attacker: avoid actions that are visible to the
compromised account (such as email notifications to a changed address)
until containment is in place.

## 3. Eradicate

- [ ] Remove attacker-added payees and revert attacker-changed account
      details (email, phone) after verifying ownership with the customer.
- [ ] Rotate any credentials or API keys that the attacker session may
      have touched.
- [ ] Review how the attacker got in: credential stuffing, phishing,
      SIM swap, or malware. Close the specific gap (for example, enforce
      MFA for the attack path, block the phishing domain).
- [ ] Confirm no persistence: no new API tokens, no new trusted devices,
      no forwarding rules on notification emails.

## 4. Recover

- [ ] Restore the account to the verified owner with fresh credentials
      and MFA.
- [ ] Release legitimate held transfers; re-issue any transfer the
      customer confirms as theirs.
- [ ] File recall or dispute paperwork with the payout rail partner for
      fraudulent transfers, inside the rail's window.
- [ ] Monitor the account closely for 30 days: alert on any new payee,
      new device, or transfer above the customer's historical norm.

## 5. Lessons learned

Hold the review within 5 business days. Answer in writing:

- Which detection fired first, and how long after the first malicious
  action? Which detection should have fired but did not?
- Was the new-payee cooling period or step-up auth bypassed, and how?
- What one rule or control change would have stopped this class of
  attack earlier?
- Update this runbook with what you learned, and add a regression test
  to the detection suite that replays the attacker's pattern.

## Communication

- Internal: incident channel, updates every 30 minutes during active
  containment.
- Customer: single point of contact, plain language, no speculation
  about attribution.
- Regulatory: engage legal and compliance early; money transmission
  businesses have reporting obligations that vary by jurisdiction.
  When in doubt, escalate.
