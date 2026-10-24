---
description: End a session — verify, update STATUS, log friction and facts, record insights
---

1. Run `engineering-paved-path:verify-done`: every check the change touches, each command with
   its quoted result line.
2. Update `STATUS.md`: the refresh header gets the current ISO time, this session, and the exact
   command with its result line. Move lines between Works now / In progress / Blocked / Next.
   Every "Works now" line names the command that proves it.
3. Append to `docs/FRICTION.md` anything hit with the Boson API this session (date, area, what
   happened, expected, doc link, severity).
4. Move every newly confirmed API fact into `docs/boson-protocol.md` with its evidence. A fact
   seen on the wire gets `VERIFIED-RUN (date)` and the quoted event; a fact read in docs gets
   `VERIFIED-DOCS (date)` and the URL.
5. Run `engineering-paved-path:engineering-insights` for `factory/INSIGHTS.md`. "Nothing worth
   recording" is a valid outcome.
6. Never mark anything done without a quoted result line.
