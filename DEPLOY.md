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
- **Grow:** כשהחיבור יהיה מוכן, מעבירים ב-Render את `GROW_MODE` ל-`live`, ממלאים את משתני `GROW_*`, וכתובת ההתראות היא `https://<netlify>/api/grow/notify`.
- **גיבוי:** Neon שומר היסטוריה של מסד הנתונים. כדאי מדי פעם גם להוריד גיבוי עם `pg_dump`.
