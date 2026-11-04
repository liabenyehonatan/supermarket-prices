# הקמת Google Analytics 4 לאתר סלי

## 1. פתיחת חשבון ונכס
1. היכנסו ל-https://analytics.google.com עם חשבון הגוגל שלכם.
2. **Start measuring** (או Admin ← Create ← Account) ← שם חשבון, למשל `Sali`.
3. **Create property**: שם `Sali`, אזור זמן Israel, מטבע ILS.
4. בשאלות על העסק בחרו את מה שמתאים (Retail / Small). המטרה: Examine user behavior.
5. **Create a web data stream**: כתובת האתר שלכם ושם `Sali web`. השאירו Enhanced measurement דולק.
6. העתיקו את **Measurement ID**, בצורה `G-XXXXXXXXXX`.

## 2. חיבור לקוד
בקובץ `.env` בשרת:

    GA_MEASUREMENT_ID=G-XXXXXXXXXX

ואז `docker compose up -d --build frontend nginx`. ה-ID נכנס ל-index.html בעת הפעלת הקונטיינר.
ריק = גוגל אנליטיקס כבוי והאתר לא טוען דבר מגוגל.

## 3. אירועים שנשלחים (frontend/src/lib/track.ts)
| פעולה באתר | אירוע ב-GA4 | פרמטרים |
|---|---|---|
| מעבר בין דפים | page_view | page_path |
| חיפוש מוצר | search | search_term |
| פתיחת עמוד מוצר | view_item | items[0].item_id = ברקוד |
| הוספה לסל | add_to_cart | items[0].item_id |
| השוואת סל | basket_compare | item_count |
| סריקת ברקוד | barcode_scan | result = found / not_found |
| פתיחת מבצע | select_promotion | promotion_name = שם הרשת |
| וייז / גוגל מפות / משלוח | outbound_click | link_type = waze / google_maps / delivery |

אותם אירועים נשמרים גם בסטטיסטיקה הפנימית (`/stats`).

## 4. אחרי הפריסה
1. **Admin ← DebugView** ופתחו את האתר עם התוסף Google Analytics Debugger, או פשוט Reports ← Realtime. האירועים אמורים להופיע תוך שניות.
2. **Admin ← Events**: סמנו כ-**Key event** את `basket_compare` ואת `add_to_cart`. אלה ההמרות החשובות.
3. **Admin ← Custom definitions**: הוסיפו Custom dimension (Event scope) לפרמטרים `link_type`, `result`, `promotion_name`, כדי לראות אותם בדוחות. `search_term` ו-`item_id` כבר מוכרים.
4. **Admin ← Data retention**: העלו ל-14 חודשים.

## פרטיות
Google signals ופרסונליזציית פרסומות כבויים בקוד. אין באנר הסכמה. אם תרצו להתאים לתיקון 13 לחוק הגנת הפרטיות, כדאי להוסיף הודעה בדף "אודות".
