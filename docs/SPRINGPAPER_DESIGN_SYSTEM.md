# SpringPaper Design System

Version: v3.6

## Product

**中文名：** 春笺  
**英文名：** SpringPaper  
**定位：** 一款帮助中小学教师提高作文阅卷效率的 AI 工作台。  
**核心理念：** AI 提高效率，判断仍属于老师。

SpringPaper 不是展示型软件，而是高频工作台。它应该像一位安静陪伴老师阅卷的助手：温柔，但不抢注意力；好看，但不增加操作成本。

## Principles

1. **效率第一**  
   任何 UI 决策都不能增加阅卷操作成本。需要操作时突出，不需要时降低存在感。

2. **温度其次**  
   品牌人格通过短句、留白、柔和色彩表达。不要用过多装饰、动效或满屏高饱和颜色表达“可爱”。

3. **美观最后**  
   美观服务于秩序、耐看和低疲劳，而不是为了截图效果。

## Color Tokens

| Token | Use | Color |
| --- | --- | --- |
| Background | App background | `#FDF8F3` |
| Surface | Card / panel | `#FFFFFF` |
| Text Primary | Title / important text | `#2F3747` |
| Text Secondary | Body / labels | `#6F7285` |
| Border | Hairline card border | `#ECDDD7` |
| Input Surface | Textbox / entry | `#FFFDF8` |
| Primary | Main action, e.g. screenshot and score | `#F8C8DC` |
| Success | Confirm / accept result | `#B9DEC9` |
| Auto | Automation action | `#D8CCFF` |
| Danger | Stop / destructive action | `#F3A7A4` |
| Secondary | Normal actions | `#F7F4F1` |
| Info | Rare informational emphasis | `#CFE3FF` |

Accent colors should stay below roughly 10% of the visible interface. Most controls should use Secondary.

## Button Semantics

- **Primary:** Screenshot and score.
- **Success:** Accept suggested score and submit.
- **Auto:** Start automatic grading.
- **Danger:** Stop automatic grading.
- **Secondary:** Copy, clear visible log, tests, calibration, add materials, list models.
- **Info:** Reserved for rare information-heavy actions. Do not use it just for variety.

Buttons should be created through the shared SpringPaper button factory instead of ad hoc color arguments.

Button typography should stay calm. Pastel buttons must not use heavy black bold text; use regular-weight text in a softened deep gray so the action remains readable without visually shouting.

Default button metrics:

- Standard height: `46`
- Prominent height: `52`
- Compact height: `36`
- Standard radius: `22`
- Compact radius: `18`
- Small toolbar height: `26`

Interaction:

- Hover uses a slightly brighter role color.
- Press feedback is intentionally tiny: reduce height by 1px and show a hairline border.
- Do not add animation that delays repeated grading actions.

## Layout

- Avoid deep card nesting.
- Prefer one main scroll region per tab.
- Cards should group real workflows, not every field.
- In compact windows, hide explanatory text and brand details first.
- Keep the teacher's repeated actions visible before decorative content.
- Startup layout is work-first: keep the header to the product name and one quiet tagline, place tabs immediately after the header, and move daily brand copy/status notes to the bottom status area.
- Do not use the daily workspace as a website-like welcome page after the user has already configured the app.

Spacing tokens:

- Page horizontal margin: `18`
- Page vertical rhythm: `10`
- Card margin: `8 x 6`
- Card inner margin: `14`
- Control vertical rhythm: `6`
- Compact margin: `4 x 3`

Compact behavior:

- Hide brand details, daily copy, and explanatory subtitles.
- Keep a lightweight bottom status line available; do not reserve a large top prompt card for calibration text.
- Reduce card radius and remove card borders/backgrounds so the page behaves like a work surface.
- Keep form controls and repeated grading actions reachable before decoration.

Repeated grading actions should be reachable from the log/monitoring page. When a teacher is watching model output, they should be able to accept, continue, or stop without switching tabs.

## Brand Personality

Daily copy should be short, quiet, and stable for the day. It should never interrupt work.

Examples:

- 今天也请相信自己的判断。
- AI 提高效率，判断仍属于老师。
- 愿每一篇作文，都被温柔阅读。
- 连评前，记得喝口水。

## Iconography

SpringPaper uses text-first controls. Functional buttons and tab names should not rely on emoji because emoji rendering varies across Windows versions and can make compact layouts unstable.

Current rule:

- Tabs use short plain Chinese labels.
- Buttons use concise action verbs, not decorative icons.
- Cards use workflow names, not visual ornaments.
- Emoji can appear in brand exploration, onboarding, or future logo studies, but not in repeated grading controls.
- If icon assets are introduced later, they should be a small custom line icon set or a stable icon font, not mixed emoji.

## Logo

The first SpringPaper logo direction is a quiet letter-paper mark:

- A cream sheet of paper with a gently folded corner.
- A soft apricot paper edge.
- A sage-green ribbon across the page, suggesting reading, pacing, and care.
- A small cherry-blossom accent, used as warmth rather than decoration.
- No pen, robot, circuit, or explicit AI symbol.

Assets:

- `assets/springpaper_mark.svg`: square mark for future app icon or compact use.
- `assets/springpaper_logo_lockup.svg`: horizontal lockup with 春笺, SpringPaper, and the tagline.

Usage guidance:

- Use the mark sparingly. It should identify the product, not compete with grading controls.
- Do not place the full lockup inside compact grading mode.
- Avoid adding more floral elements elsewhere; the blossom belongs to the logo system.

## Roadmap

- **v3.1:** Establish Design System and semantic colors. Done.
- **v3.2:** Normalize buttons and micro-interactions. Done.
- **v3.3:** Reduce card nesting and unify whitespace. Done.
- **v3.4:** Normalize icon usage. Done.
- **v3.5:** Refine brand personality and explore a SpringPaper logo. Done.
- **v3.6:** Make startup layout work-first and soften button typography. Done.
- **Future:** Focus Mode: hide explanation, stats, and decoration; keep only screenshot, submit, auto grading, and stop.
