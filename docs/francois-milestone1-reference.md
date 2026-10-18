# SIB — Milestone 1: Client Source Reference (French → English)

Prepared Oct 19, 2026. Companion to `francois-client-materials-reference.md`.

Rule for this file: every statement cites the exact source (file, section, and where useful the original French). Where a source is ambiguous, contradicts another source, or is only a suggestion, that is stated. Nothing here is inferred without being labelled as such.

---

## 0. Sources used

| # | Source | Location | What it is |
|---|---|---|---|
| S1 | `Scope_of_Work__v6_2_.md` | uploaded | Our SoW, Milestone 1 table and hours |
| S2 | `SIB_Maintenance_App___Handover__Oct_19__2026_.md` | uploaded | Our team's handover: build status, decisions, open questions |
| S3 | `guide-coordonnateur-maintenance-v4_39.md` | Drive ID `1c1VA1HofAbsT1FnurxczM9VVw1asq5T5` | The client's AI coordinator guide (rules for their current Claude triage). Header: "Version 4.39 — 22 août 2026". Line numbers below refer to this file. |
| S4 | `Présentation Cahier de Charges – 2026/08/27 09:01 EDT – FR` | Drive ID `18TfIoy81d619WAgcYlNS0-uXT8dUocyNG1K77RFToL0` | Aug 27, 2026 meeting (François, Jérémi, Oktay): Gemini notes + transcript. Timestamps below refer to this transcript. |
| S5 | `Francois Notes Maintenance` | Drive ID `1gFlEa4BiUstCeoxrNwV13Lwvbq7btcsPz3YCAVusNi4` | François's own working notes. Contains sections he wrote himself AND sections headed "Notes Claude Latchel" / "Notes Claude Property Meld", which are AI-written research he pasted in. These two kinds are kept separate below. |
| S6 | `Tableau des Appels de services urgents Soluvox.xlsx` | Drive ID `1OTk-X__g5vLMsr5wrJe2e5-rRbBhm47_` | Export of Soluvox (after-hours answering service) urgent call log. An English copy also exists: `Urgent Service Call Log - Soluvox.xlsx` (ID `11d42VwxvpkT_69dsBdSwiBXCEZ2Y6Hue`). |

---

## 1. Milestone 1 status at a glance

Status column comes from S2 (our handover), not from the client. "Client source" says what the client materials contain for that item.

| SoW item (S1) | Status (S2) | Client source available? |
|---|---|---|
| 3.1 Intake + 4-axis taxonomy | Partial (testing). Taxonomy dropdowns blocked on client | Taxonomy: only an AI-drafted suggestion, not confirmed values (§2) |
| 3.2 Calendar & core dispatch | Done (dispatch actions, routing) | — |
| 3.3 AI triage | Trigger done; AI-notes feedback next | Guide S3 is the rulebook (already in repo per S2) |
| 3.4 Weather escalation | Not started | Yes, a draft rule table in S5, explicitly "to validate with Charles" (§4) |
| 3.5 En route | Out of scope (no technician portal) | Yes, S4 + S5 describe it (§5); needed for 3.6 elapsed time |
| 3.6 Closeout / follow-up | Not started | Yes, 4 outcomes defined by François in S5 and S4 (§6) |
| 3.7 After-hours / emergency | Unknown in handover | Yes, S3 §5, S4, S5, S6 (§7) |
| 3.8 SSO / auth | Done (auth hardening) | S4 00:45:22: 2FA by email confirmed |
| 3.9 QA / UAT / cutover | Go-live checklist in S2 | — |
| 3.10 Decision justification | Done | S4 00:33:24–00:34:59 confirms requirement |
| 3.11 Survey + technician KPI | Not listed in S2 status table | Yes, S4 + S5 (§8); contradiction on Google reviews |

---

## 2. Intake (3.1) — taxonomy and categories

### 2.1 The 4-axis taxonomy: what actually exists

Source: S5, section "Notes Claude Property Meld", §1.1 "La découverte structurante : la taxonomie à quatre axes".

- The four axes, verbatim: « élément, symptôme, composante et emplacement » → element, symptom, component, location.
- Recommended implementation, verbatim: « quatre colonnes dans l'onglet CALLS (element, symptome, composante, emplacement), alimentées par des listes déroulantes en cascade » → four columns fed by cascading dropdowns. This confirms the axes are dependent (cascading), per the text.
- Starting value list offered: about 15 elements (plomberie, chauffage, électricité, serrurerie, appareils, revêtements, portes/fenêtres, extermination, ventilation, aires communes, extérieur, ascenseur, sécurité incendie, dégât d'eau, autre) → plumbing, heating, electrical, locksmithing, appliances, surfaces/coverings, doors/windows, extermination, ventilation, common areas, exterior, elevator, fire safety, water damage, other. "4 to 8 symptoms per element", "a list of components per element" (not provided), and a closed location list: cuisine, salle de bain, chambre 1-4, salon, entrée, balcon, sous-sol, corridor, buanderie, stationnement, extérieur → kitchen, bathroom, bedroom 1–4, living room, entrance, balcony, basement, corridor, laundry room, parking, exterior.

**Proof of status:** the list is labelled « Point de départ suggéré … (jugement professionnel, à valider avec Charles Bergeron) » → "suggested starting point (professional judgment, to validate with Charles Bergeron)". It is AI-written research inside François's notes, not a client-approved list. No symptom or component values exist anywhere in the sources reviewed. The coordinator guide S3 contains no 4-axis lists (searched for symptôme, composante, emplacement, taxonomie: no taxonomy hits).

**Conclusion:** taxonomy dropdowns remain blocked on Charles. We can show him the S5 draft as a starting point to approve or edit.

### 2.2 "Charles's categories" — the only category list found

Source: S3 §6b "Règles d'attribution automatique par catégorie" (lines 460–481).

- It is a "living table" that « seul le coordonnateur ajoute, modifie ou retire » → only the coordinator adds, edits or removes rules.
- Rule A4 lists 22 categories routed to the default coordinator, verbatim list translated: cigarette smell · intercom · fire alarm · alarm panel · smoke detector · padlock keys · remote/fob ("manette") · extermination · bulky-item pickup · garbage-chute smell · elevator/freight-elevator trouble · Bell · Vidéotron · Internet · appliance trouble · snow · lawn · exterior maintenance · window washing · building cleanliness · parking surface condition · pruning and vegetation.
- Other rules: A1 complexity C1 tasks; A2 gym equipment → Body Gym; A3 doors/windows replacement certain → Duclos; A3b doors/windows unknown cause → sector maintenance man diagnoses first; A5 dedicated perimeters.

**Not stated in any source:** whether this table is what "Charles's categories" refers to. Ask Charles.

### 2.3 Other intake facts from the client

| Fact | Source |
|---|---|
| Four standard entry-permission codes: "Autorisé en tout temps sans restriction" (authorized any time), "Présence du locataire exigée" (tenant presence required), "Logement vacant — accès libre" (vacant, free access), "Espace commun — aucune coordination locataire requise" (common area, no tenant coordination) | S3 §9 note format, PERMISSION D'ENTRÉE |
| « Ignorer À JAMAIS la mention « (traitement prioritaire) » du formulaire Gravity » → always ignore the "(priority handling)" label coming from the Gravity form | S3 §9, same block |
| Gravity requests are numbered ASNU#####; the original request sits at the bottom of the calendar event: request number, access permission, animals, problem, requester, phone, creation date | S3 §2 "Structure des descriptions" |
| "Call niveau 2" concept to integrate in MAIN1: heavier calls (vacant renovation, water damage, heavy work, tenant complaint, put in priority), with named people: Sonia, Marc and Zac, Betim, Christian St-Laurent, Mamouhd, Jean Menada | S5, section MAIN1 (François's own text) |
| "MAIN AJOUT" marked « ESSENTIEL »: add-on to an existing open call ("Ajouter à calls existants"), today it edits the call and emails info@; whether to notify the assigned worker is "à valider" (to validate) | S5, MAIN1 |
| Unit history + open calls when placing a call: marked « NICE-TO-HAVE » | S5, MAIN1 |
| Recurring calls: open question addressed to Charles, « Quels seraient nos besoins précisément ? » | S5, MAIN1 |
| François (Aug 27): the Gravity form can stay on the website but should route to customer service, who then create the call in the app; Jérémi proposed the public form feed the app as "draft/pending"; François agreed « ça peut être ça aussi direct. C'est encore mieux » (that works too, even better) but said he is worried about a public link | S4 00:27:45–00:31:05 |

Note: S2 records "Gravity Forms form and WordPress can't be changed" as a client constraint. S4 does not contradict that; it discusses future options only.

---

## 3. Urgency tiers — the sources disagree

| Source | What it says |
|---|---|
| S5, "SKILL DU TRI", François's own text | Three tiers: « URGENT: une vraie urgence, a faire immediatement » (a real emergency, do immediately); « AJD: c'est la priorite du jour » (priority of the day); « ajd: prioritaire mais pas necessairement aujourd'hui » (priority but not necessarily today) |
| S3 §2 title table (line ~285) | « Urgent / urgence dans le titre — Traiter comme AJD » → "Urgent" in a title is treated as AJD. Only two tiers in practice. |
| S3 §9 step 2 (lines 560–563) | AJD = actively running water including indirect signs (sound of dripping in a wall, growing damp stain, sagging ceiling), backflow, heating or hot-water failure, person stuck, alarm/fire, non-working lock, dead fridge, danger. ajd = contained slow leak, mould, non-critical faulty appliance, vermin (always), AC during a heatwave. No mention = keys, fobs, screens, cosmetic, etc. |

Consequence for the handover's open item "meaning of 'urgent'": François's notes define URGENT as a tier above AJD; the guide (dated later, Aug 22) flattens it to AJD. Ask which one the app should store. The handover's rule "26 calls with raw 'urgent', don't map" stays correct until answered.

Handover question "dripping faucet = AJD, intended?": S3 does not mention faucets. The relevant lines are "eau qui coule activement" (AJD) vs "fuite lente contenue" (ajd). Which one a dripping faucet falls under is not stated. Still open.

---

## 4. Weather-triggered escalation (3.4)

### 4.1 Where the SoW rule comes from

Source: S5, section "Notes Claude Latchel", §2.3 « La vérification météo — la pépite québécoise ». This is AI-written research pasted by François, not François's own words.

Key statements (translated):
- "No heat" in October at 14 °C is not the same urgency as "no heat" in January at −27 °C with wind chill; the second is an emergency under Civil Code art. 1865 (tenant must allow urgent and necessary repairs) and engages the landlord's liability under art. 1864.
- Proposed implementation: on creation of a heating-category call, call a weather API for current temperature and 24-hour forecast in Québec or Lévis, then apply a rule.
- Draft table, verbatim label « Ébauche à valider avec Charles Bergeron » (draft to validate with Charles Bergeron):

| Forecast outdoor temp (24 h) | "No heat" call |
|---|---|
| Below −15 °C | Critical emergency — same-day intervention, on-call activated after hours |
| −15 °C to −5 °C | Emergency — within 24 h |
| −5 °C to +10 °C | Priority — within 48 h |
| Above +10 °C | Normal — regular scheduling |

- Same logic proposed for pipe freezing (forecast drop below −20 °C), snow removal (forecast accumulation), and AC in heatwaves. No thresholds given for those three.
- Weather API: « la disponibilité et le coût d'une API météo appropriée — Environnement Canada offre des données publiques … — n'ont pas été vérifiés en détail. À valider avec Agentyx. » → availability and cost not verified; to validate with us.
- Rated "Effort S", "Should" for MVP.

### 4.2 What else the client said

- S4 00:34:59 (Jérémi to François): weather urgencies are "un peu inclus" (somewhat included). François did not add thresholds in that meeting.
- S3 has no temperature rules. It classes « panne de chauffage/eau chaude » (heating/hot water failure) as AJD regardless of temperature, and « clim en canicule » (AC in heatwave) as ajd (§9 step 2).

### 4.3 Dependencies (from the sources above)

- A heating category on the call. The taxonomy (§2) is not confirmed, so the trigger has no confirmed field yet.
- Québec vs Lévis location: S5 names both cities; buildings carry a sector/territory (S3 §3, Lévis = orange).
- "On-call activated after hours" depends on 3.7 (§7).
- Thresholds are unvalidated; Charles must approve them.

---

## 5. "En route" (3.5) — out of scope, recorded for the scope-change note

S2 marks 3.5 out of scope (no technician portal). Client requirements, for the record:

| Requirement | Source |
|---|---|
| Add an "En route" button in each call and connect it to Quo (phone/SMS tool); test with Nicolas Rousseau | S5 (François's text, list near "Wispr Flow") |
| If possible the form is geolocated; record hours and dates and the previous call, to rebuild a call-by-call log | S5, section EN ROUTE |
| Message template start: « Bonjour, Ce message est destiné aux occupants, aux locataires du XXX. » (Hello, this message is for the occupants/tenants of XXX) | S5, EN ROUTE |
| Clicking should put an "X" in front of the call automatically, « comme on fait en ce moment » (as we do now). S3 §2 confirms: prefix X = the worker is doing the call now, don't move or reassign | S5 EN ROUTE; S3 §2 |
| Time measured between "en route" and final follow-up, for duration, calls per technician per day, and client billing | S4 00:57:02; S4 decisions « Mesure systématique du temps d'intervention » |

**Impact on 3.6 (stated in sources, not inferred):** the client defines intervention time as en route → follow-up (S4 00:57:02). With en route dropped, 3.6 has no start timestamp for elapsed time. Include this in the scope-change note to François.

---

## 6. Closeout / follow-up (3.6)

### 6.1 The four outcomes (François's own definition)

Source: S5, section "MAIN Follow Up". Confirmed orally in S4 00:35:49–00:38:44, where François says « Il y en a quatre » (there are four).

| # | Original | Translation | What happens |
|---|---|---|---|
| 1 | CALL FERMÉ TERMINÉ COMPLÈTEMENT | Call closed, fully completed | « Le call tombe en gris. C'est fini » — call turns grey, done |
| 2 | CALL PARTIELLEMENT FAIT, JE DOIS REVENIR | Partially done, I must come back | The worker reschedules his own call directly |
| 3 | CALL PARTIELLEMENT FAIT, BESOIN D'UNE EXPERTISE (option Urgente) | Partially done, needs expertise (urgent option) | Returns to the maintenance mailbox with the worker's comments and call link; coordinator decides and re-dispatches; ideally analysed by AI with next-step advice |
| 4 | CALL PAS DU TOUT FAIT, BESOIN D'UNE EXPERTISE / ENVOYER A DISPATCH (option Urgent) | Not done at all, needs expertise / send to dispatch (urgent option) | Same as 3, worker could not do the call |

S4 Gemini notes list them as "complété, partiellement complété, besoin de retour, expertise requise".

**Discrepancy:** S1 (our SoW) says three outcomes, "complete / partial-reschedule / failed". The client defines four, with an urgent flag on #3 and #4. The client's version should win; the SoW wording should be corrected.

### 6.2 Other closeout requirements

| Requirement | Source |
|---|---|
| Worker explains the call and next steps by dictation (Wispr Flow) | S5 MAIN Follow Up |
| Option for the worker to text the tenant directly, copy to maintenance, and noted in the call (example: « je viens de vous laisser votre puce dans votre boîte postale » — I just left your fob in your mailbox) | S5 MAIN Follow Up |
| Mandatory photos in the follow-up form whenever a technician leaves; taken or uploaded in-app, not saved to the phone gallery | S4 decisions « Photos obligatoires dans le formulaire »; S4 00:55:30–00:56:18 |
| Elapsed time en route → follow-up | S4 00:57:02 (see §5) |

### 6.3 How closeout works today

| Fact | Source |
|---|---|
| Each triaged calendar event starts with a "FOLLOW-UP TERRAIN" block: title plus about 8 blank lines where the field worker writes his report after the call; future home of a link to a follow-up Web App | S3 §9, "SECTION 1 sur 3" (line ~581) |
| « seul un humain met un appel en gris » — only a human turns a call grey (done) | S3 §3 colour table |
| A "Web App formulaires terrain" (field forms web app) exists and parses the OCCUPANTS tag from events | S3 §11 and §13 item 1. Its content was not found in the Drive. |
| The follow-up form « existe pas encore » (doesn't exist yet) and is done "broche à foin" (makeshift); some workers do it well, some badly; François wants it standardized | S4 00:36:46–00:38:44 |

**Not found in any source:** how Majordome (st_maj) reports a job as done. Still open (S2).

---

## 7. After-hours / emergency handling (3.7)

### 7.1 Today's on-call system

Source: S3 §5 "Rotation de garde" (lines 424–428), translated:
- Red blocks titled "XXXX Call urgence" show which employee is on call for the period.
- On-call changes Wednesday before 4 pm and Friday before 4 pm, cc heidy.berube@sibelanger.com and info@sibelanger.com.
- The on-call employee handles evening/weekend emergencies; "X" prefixes often appear on their ongoing interventions.

S3 §11: an Apps Script "SOLUVOX - GMail Maintenance" is linked to the Soluvox emergency answering service.

### 7.2 The Soluvox log (S6) — structure, translated

One sheet "Appels urgents Soluvox", 11,102 rows, call dates from 2021-01-01 to 2026-09-15 (counted in the file).

| French column | English |
|---|---|
| Date de l'appel / Heure / Journée | Call date / time / weekday |
| Plage de service | Service period: "Jour" (day) 4,540 rows, "Soir & FDS" (evening & weekend) 6,562 |
| Plage horaire | Time slot: "De jour (7h à 17h)" 7,652; "De soir (17h01 à 23h)" 2,961; "De nuit (23h01 à 6h59)" 489 |
| Nom de l'appelant, Téléphone 1 (+ international format) | Caller name, phone |
| Numéro d'appel | Soluvox call ID |
| Adresse, Numéro d'unité ou d'appartement | Address, unit number (free text) |
| Peut-on entrer si absent? | Can we enter if absent? (En tout temps / Non / Oui avec un délai de 24h / Ne s'applique pas) |
| Avez-vous des animaux? / Si oui, quel type? | Pets? / which type |
| Urgence et adresse confirmées selon la FAQ? | Emergency and address confirmed per FAQ? |
| J'ai avisé des frais, si applicable | I informed of fees, if applicable |
| Tentative Garde 1–4 | On-call attempts 1 to 4: each holds status, forwarded-to name, timestamp |
| Message | Free-text message |
| Nombre de portes du portefeuille | Number of doors in portfolio: 3860 in every row |

Attempt-1 status counts: "Appel transmis" (forwarded) 10,735; "Appel non-transmis" 364; "Garde particulière non-disponible" 3. Most frequent attempt-1 recipients: "Coordonnateur maintenance" 4,417, then named employees (Alexandre Theriault 1,135, Pierre Boudreault 586, Mahmoud Chachia 524, …).

Unexplained in the file: 1,094 weekday rows are "De jour (7h à 17h)" but labelled "Soir & FDS", spread over 492 different dates. The file does not say why.

Portfolio size note: S6 says 3,860 doors. The "4 300 logements" figure appears in S5 inside the AI-written "Notes Claude" sections, not in client data.

### 7.3 What François asked for

| Requirement | Source |
|---|---|
| « Chaque call d'urgence doit automatiquement générer un MAIN Urgence » — every emergency call must automatically generate a MAIN Urgence (record) | S5, MAIN Urgence |
| Current procedure: for every urgent call that passes Soluvox's filter, the on-call worker must email maintenance@sibelanger.com what happened and his conclusion; they often forget (example: 3 urgent calls on a weekend, only 2 emails) | S4 00:40:24–00:42:36 |
| Short term: an in-app form; the worker logs in, picks the unit or building, dictates what happened | S4 00:42:36–00:43:25 |
| Soluvox also sends an automated report from its CRM to the maintenance mailbox | S4 00:40:24 |
| The on-call chain can change daily (first person, then next if no answer, finally the coordinator); OpenPhone could not do efficient cascades | S4 00:43:25–00:44:22 |
| Long-term goal: replace Soluvox entirely with Agentyx voice AI | S4 decisions/details; 00:39:29 |

The S1 wording "automated next-morning coordinator report" does not appear in S4 or S5. The closest client statements are the per-call email report and Soluvox's automated CRM report above.

### 7.4 AI-drafted escalation design (suggestion only)

S5, "Notes Claude Latchel" §2.4: proposes a GARDE tab (week, on-call employee, replacement, period), an escalation rank per supplier by trade and sector, a timed escalation (no acknowledgement after X hours → notify next and alert coordinator; example 2 h urgent vs 24 h standard), and business hours as a parameter so on-call only activates after hours. This is AI research, not a client decision.

### 7.5 Data the sources show exists vs missing

- Exists: Soluvox time-slot definitions (S6), on-call change days (S3 §5), on-call red blocks in the main calendar (S3 §3, §5).
- Not found: business hours as a written rule, a holiday list, an on-call schedule outside the calendar, the Soluvox email exchange François promised to forward (S4 next steps: « Partager courriel Solivox »).

---

## 8. Satisfaction survey + technician KPI (3.11)

| Requirement | Source |
|---|---|
| Survey at the end of each call confirmed for version 1 | S4 decisions « Sondages de satisfaction client » |
| Three questions: was the person polite, overall satisfied, was the problem solved; plus a comments field | S4 00:54:49–00:55:30 |
| Satisfaction becomes a contractual KPI per technician, visible to managers; technicians can see their own score and comments | S4 00:55:30 |
| Satisfied tenants receive a Google review link | S4 00:57:02 ("il est convenu" — it was agreed); François adds it is "like V2, but very easy" (00:57:43) |
| François's own notes: 5-star survey; 5 stars → Google review; under 5 stars → address the problem | S5, URGENCES item 3 |

**Contradiction:** S5 "Notes Claude Latchel" (AI-written) recommends « Garde le sondage de satisfaction comme outil de gestion interne, ne le connecte pas à Google Avis » (keep it internal, don't connect it to Google reviews). François's own notes and the Aug 27 meeting both say to send satisfied tenants to Google. François's statements are the client position; the AI note is not.

**Not found:** who triggers the survey and through which channel (SMS/email). With no technician portal and no en route, the closeout trigger is unclear. Ask.

---

## 9. Evidence on handover open questions (S2)

| S2 open question | What the sources show | Still open? |
|---|---|---|
| Does "send to Majordome" mean assign to Mahmoud? | S3 rule 35 table (line 210): st_maj calendar = « appels confiés à Majordome Québec — grosso modo tout ce qui est sur la rive-sud de Québec » (calls entrusted to Majordome Québec, roughly all of the south shore). S3 §6b A5(c): south shore (Lévis, Charny…, orange territory) → MACH (Mahmoud Chachia), all calls. S3 §4 line 411: MACH = self-employed, assigned to all south-shore calls + Ste-Foy. S3 line 197: st_maj titles carry the worker prefix « MACH, etc. » ("etc." suggests other names may appear). S5 lists "Majordome" separately from named subcontractors under « SOUS-TRAITANTS sur Mobile Punch ». | Yes. Strong link to Mahmoud, but no source says Majordome = only Mahmoud. |
| Is the old AI coordinator still writing notes into the calendars? | S3 §13 item 6: a scheduled Claude Cowork task triages autonomously since July 16, 2026, hourly 7:00–17:00 (tightened Aug 22). Rule 35: writing is authorized in both main and st_maj calendars. | Was active as of the guide (Aug 22; file dated Sep 1). Current status unknown. |
| Meaning of "urgent" | See §3: URGENT is a top tier in S5; S3 treats it as AJD. | Yes, conflicting sources. |
| Taxonomy values and dependencies | §2.1: only an AI-drafted suggestion; cascading per S5. | Yes. |
| Call types ("Charles's categories") | §2.2: S3 §6b is the only category list found. | Yes, unconfirmed match. |
| How Majordome reports a job done | Not found. General practice: FOLLOW-UP block in the event; only a human greys a call (§6.3). | Yes. |
| Who schedules an undated Majordome call | Not found. S5 says each maintenance employee manages his own schedule and moves his own calls; whether that applies to Majordome is not stated. | Yes. |
| Dripping faucet = AJD? | §3: guide has no faucet rule. | Yes. |
| Record 3.5 as dropped | §5 lists what the client asked for; note the 3.6 elapsed-time dependency. | Needs François's sign-off. |
| "To redo" closeout outcome | §6.1: client defines "partially done, I must come back" (worker reschedules himself). | Partly answered; confirm wording. |
| Satisfaction survey | §8. | Trigger/channel open. |

## 10. Other conflicts found (for the record)

- S3 §2: « un call n'est JAMAIS assigné à deux personnes » (never assigned to two people). S5 MENAGE: « souvent on a 2 personnes attitrées sur le même call » (often two people on the same call). Context differs (cleaning calls), but the data model should not assume one assignee everywhere without asking.
- S1 (SoW) closeout: 3 outcomes; client: 4 (§6.1).
