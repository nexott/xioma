# xioma model changer — pack

Пак читается скриптом автоматически: `PLAYER → Models → Refresh from GitHub`
(при старте скрипт грузит его сам, кнопка — для принудительного обновления).

Источник: `https://raw.githubusercontent.com/nexott/xioma/main/models/models.json`

## Что внутри

- `anime_a`, `anime_b`, `anime_c` — три полноценные VRoid-модели (настоящие
  аниме-персонажи, ~25-28k треугольников, атлас 4096x4096). Разобраны на части
  тела по костям: Head (с волосами), Torso (с одеждой), руки, ноги.
  Ноги двигаются стандартными R6-анимациями, пивоты суставов анатомические
  (плечи/бёдра/шея), оружие цепляется в правую руку.
- `models.json` — манифест: список моделей + оружия.

## Формат models.json (kind: custom)

- `parts` — части R6-рига: `part` = `Head | Torso | Right Arm | Left Arm |
  Right Leg | Left Leg`; `mesh`/`texture` — файлы из репо (бинарный Roblox
  .mesh v2.00 + png), `meshId`/`textureId` — id каталога, `scale`, `color`,
  `transparency`, `size`.
- `center: [x,y,z]` — анатомический пивот части (стады; корень модели (0,0,0) =
  HumanoidRootPart, земля на y = -3). Вокруг него вращается сустав: для рук —
  плечо, для ног — бедро, для головы — шея.
- `rot: [rx,ry,rz]` — поворот части в позе покоя (радианы); руки конвертированных
  моделей опущены из T-поза (~15°).
- `extra` — доп. детали: `attach`, `offset: [x,y,z,rx,ry,rz]`.
- `thumb` — превью (png).

## weapons[]

`asset` — id модели-оружия из каталога, `grip` — позиция/поворот относительно
плеча правой руки (радианы), `hold` — id анимации удержания (182393478 — R6
Tool Hold). Grip подобран под конвертированные модели: y ≈ -2.0 (плечо → кисть).
Если оружие сидит криво — правь grip в models.json и жми «Refresh from GitHub».

## Как добавить свою модель (VRM -> pack)

1. Возьми VRM (например, VRoid-модель со свободной лицензией).
2. `python3 tools/vrm2r6.py model.vrm models/anime_d "Anime Girl D"`
   — скрипт разберёт модель по костям, соберёт атлас текстур и запишет
   .mesh + tex.png + thumb.png + entry.json.
3. Добавь entry.json в models.json и загрузи папку в репо.
4. В игре: «Refresh from GitHub».

## Проверенные модели

Anime Girl A / B / C (VRoid sample avatars, свободная лицензия) + оружие:
Deagle, AK-47, Katana, Hunting Rifle. Каталожные модели добавляются через
«Add by ID» в меню.
