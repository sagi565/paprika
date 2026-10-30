# העלאה לאוויר: Netlify + Render + Neon

הכל בחינם ועם HTTPS אוטומטי.

| חלק | איפה | כתובת לדוגמה |
|---|---|---|
| האתר (React) | Netlify | `https://paprika-perot.netlify.app` |
| השרת (FastAPI) | Render | `https://paprika-api.onrender.com` |
| מסד הנתונים | Neon | (פנימי) |

Netlify מעביר כל בקשה של `/api/...` ל-Render. מבחינת הדפדפן הכל באותה כתובת, וכך ההתחברות עובדת.

**שימו לב:** השרת החינמי של Render נרדם אחרי 15 דקות בלי שימוש. בכניסה הראשונה אחרי הפסקה מופיע "השרת מתעורר, עוד רגע…", וזה לוקח עד דקה. האתר מנסה שוב לבד.

---

## 0. GitHub

Render ו-Netlify מושכים את הקוד מ-GitHub.

1. יוצרים ריפו **פרטי** חדש ב-GitHub, למשל `paprika`.
2. מעלים אליו את תיקיית `paprika`. הקובץ `.env` עם הסיסמאות **לא** עולה, כי הוא מוחרג ב-`.gitignore`.

## 1. Neon: מסד הנתונים

1. נרשמים ב-https://neon.tech, ויוצרים פרויקט בשם `paprika` באזור **AWS Europe Central (Frankfurt)**.
2. ב-**Connection string** מעתיקים את הכתובת שמתחילה ב-`postgresql://`.

## 2. Render: השרת

1. נרשמים ב-https://render.com עם GitHub.
2. בוחרים **New → Blueprint**, ואז את הריפו `paprika`. הקובץ `render.yaml` מגדיר את הכל.
3. ממלאים את שני הערכים שהוא מבקש:
   - `DATABASE_URL`: הכתובת מ-Neon.
   - `ADMIN_PASSWORD`: סיסמת הכניסה לאתר. בוחרים סיסמה חזקה.
4. מחכים שהבנייה תסתיים, ובודקים שהכתובת `https://<השם-שלכם>.onrender.com/api/health` מחזירה `{"ok":true}`.
5. רושמים את הכתובת. היא תשמש בשלב הבא.

## 3. Netlify: האתר

1. נרשמים ב-https://netlify.com עם GitHub.
2. בוחרים **Add new site → Import an existing project**, ואז את הריפו `paprika`. ההגדרות נקראות מ-`netlify.toml`.
3. לפני ה-Deploy, ב-**Environment variables**, מוסיפים:
   - `API_ORIGIN` = כתובת ה-Render מהשלב הקודם, בלי `/` בסוף.
4. מריצים Deploy.
5. כדי לבחור כתובת עם "paprika": **Site configuration → Change site name**. השם `paprika` כנראה תפוס, אז אפשר לנסות `paprika-perot`, `paprika-fruits` או `paprika-veg`.

## 4. בדיקה

- נכנסים לכתובת של Netlify, מתחברים, ומוסיפים גן.
- בטלפון: פותחים את עמוד השליחה של גן שחויב. כפתור **"שליחה בוואטסאפ"** אמור לפתוח את חלון השיתוף עם התמונה.

## אחר כך

- **שהשרת לא יירדם (רשות):** ב-https://cron-job.org אפשר להגדיר בקשה כל 10 דקות לכתובת `https://<render>/api/health`. 750 השעות החינמיות בחודש של Render מספיקות לשרת אחד שדולק כל הזמן.
- **Grow, חיוב אמיתי:** ראו את הסעיף הבא.

## 5. חיבור Grow (חיוב אמיתי)

1. **פרטי Sandbox מ-Grow:** ב-Render, תחת Environment, ממלאים:
   - `GROW_USER_ID`
   - `GROW_PAGE_CODE`
   - `PUBLIC_URL` = `https://paprika-fruits.netlify.app`
   - `GROW_BASE_URL` כבר מוגדר ל-Sandbox.
   - מעבירים את `GROW_MODE` ל-`live`.
   - שומרים, ו-Render מעלה גרסה מחדש.
2. **בדיקה ב-Sandbox:**
   - בעמוד **גנים** פותחים גן, לוחצים **שמירת כרטיס** ואז **העתקת קישור**, ופותחים את הקישור.
   - מזינים כרטיס בדיקה `4580000000000000`, חוזרים לאתר ולוחצים **בדיקה אם נשמר**. הסטטוס צריך להיות "שמור".
   - בעמוד **חיובים** מזינים סכום ולוחצים **חיוב**.
   - בודקים שהחשבונית מגיעה. אם לא, זו השאלה הפתוחה מול Grow.
3. **Production:**
   - שולחים ל-`support@grow.business` בקשה ל-Production review.
   - אחרי האישור מחליפים ב-Render את `GROW_BASE_URL` ל-`https://secure.meshulam.co.il/api/light/server/1.0`, ואת `GROW_USER_ID` ו-`GROW_PAGE_CODE` לפרטי ה-Production.
4. **לכל גן, פעם אחת:** בעמוד הגנים לוחצים **שמירת כרטיס** ואז **שליחה לגננת**. הקישור נשלח בוואטסאפ, הגננת מזינה את הכרטיס, והוא נשמר אוטומטית.

כתובות ה-Webhook ש-Grow קורא אליהן נבנות אוטומטית מ-`PUBLIC_URL` ומ-`GROW_WEBHOOK_KEY` (ש-Render יוצר לבד):
- שמירת כרטיס: `<PUBLIC_URL>/api/grow/notify?key=...`
- חשבוניות: `<PUBLIC_URL>/api/grow/invoice-notify?key=...`
- **גיבוי:** Neon שומר היסטוריה של מסד הנתונים. כדאי מדי פעם גם להוריד גיבוי עם `pg_dump`.
