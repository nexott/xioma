# xioma model changer — pack

Этот файл-пак читается скриптом автоматически: `PLAYER → Models → Refresh from GitHub`
(при старте скрипт грузит его сам, кнопка — для принудительного обновления).

Источник: `https://raw.githubusercontent.com/nexott/xioma/main/models/models.json`

## Формат models.json

```json
{
  "version": 1,
  "weapons": [
    { "name": "AK-47", "asset": 94968837017770,
      "grip": [0.1, -1.1, -0.5, -1.5707963, 0, 0], "hold": 182393478 }
  ],
  "models": [
    { "kind": "asset",  "name": "Scream", "id": 8750931560 },
    { "kind": "custom", "name": "My Rig", "thumb": "models/my/thumb.png",
      "parts":  [ { "part": "Head", "mesh": "models/my/head.mesh", "texture": "models/my/head.png" } ],
      "extra":  [ { "name": "Horns", "attach": "Head", "mesh": "models/my/horns.mesh", "offset": [0, 0.6, 0] } ] }
  ]
}
```

### models[]
- `kind: "asset"` — готовая ригованная модель из каталога Roblox (`id`). Анимации
  (ходьба/бег/прыжок) подхватываются автоматически, если в модели есть Humanoid + Motor6D.
- `kind: "custom"` — риг собирается скриптом: стандартный R6-скелет (HumanoidRootPart,
  Torso, Head, 2 руки, 2 ноги + Motor6D), поверх — твои меши. Ноги двигаются, потому
  что это стандартные R6-анимации.
  - `parts` — замена стандартных частей: `part` = `Head | Torso | Right Arm | Left Arm | Right Leg | Left Leg`;
    опционально `size: [x,y,z]`, `mesh`/`texture` — файлы из репо, `meshId`/`textureId` — id каталога,
    `scale: [x,y,z]` (масштаб меша), `color: [r,g,b]`, `transparency`.
  - `extra` — дополнительные детали (волосы, рога, капюшон...): `attach` — к какой части,
    `offset: [x,y,z,rx,ry,rz]` относительно неё (радианы), `size`, `mesh`/`meshId` и т.д.
  - `thumb` — путь к картинке-превью в репо (png).

### weapons[]
Оружие из дропдауна «Weapon» цепляется к любой модели. `asset` — id модели-оружия
из каталога (подойдут и одиночные MeshPart'ы), `grip` — позиция/поворот в руке
(относительно Right Arm, радианы — крути, пока не встанет как надо), `hold` — id
анимации удержания (182393478 — классический R6 Tool Hold; для R15-ригов
используется 507768375 автоматически).

Вместо `asset` можно описать оружие частями: `"parts": [ { "mesh": "...", "size": [...], "offset": [...] } ]`.

## Меши с GitHub

Меши — бинарный формат Roblox (`version 2.00`). Конвертер OBJ → .mesh:
`tools/obj2mesh.py` (см. справку в шапке файла). Текстуры — обычные png.

Пути в манифесте — относительно корня репо (тот же base, что и у остальных ассетов).
Кэш на клиенте чистится/обновляется автоматически; если меняешь файл — жми
«Refresh from GitHub».

## Проверенные стартовые модели

Список в `models.json` подобран так, чтобы в моделях были анимации (NPC-риги):
Scream, Ghostface, Naruto, Chainsaw Man, Makima, Ayano Aishi, Anime Girl,
Saitama, Siren Head, Cartoon Cat + оружие (Deagle, AK-47, Katana, Hunting Rifle).
Добавляй свои через «Add by ID» в меню или прямо в models.json.
