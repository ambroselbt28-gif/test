插入位置: @系统
深度: 0
顺序: 100

---
变量更新规则:
  扁平变量:
    type: 键值对
    check:
      - 状态以扁平键存储：世界指标、regret_ 后悔值、ev_ 证据、wish_ 心愿、flag_ 事实标记、hiddenWishStage
      - 每次只写本轮发生变化的键，没有变化写空对象
      - 键名逐字复制本轮注入的可写键清单，禁止自造键、翻译键名或嵌套对象
      - 证据只能 locked → obtained → public 逐级推进
      - 只有本轮正文写出了取得过程、证据实际到手，ev_ 才能变为 obtained；玩家声称已经拿到、正文却没有写出取得过程的，不改变
      - 一个回合最多一项 ev_ 从 locked 变为 obtained；公开可以在高潮场合多项同时进行
      - 心愿与 flags 只能 false → true
      - 后悔值只能增加且不超过 100
      - hiddenWishStage 只能 locked → hinted → revealed → completed 前进一格

变量输出格式:
  rule:
    - 每次普通剧情回复末尾输出一个 charx_vars JSON 块
    - JSON 为扁平键值对，只含本轮变化的键
    - charx_vars 后输出 moonlight_choices，内部为固定 3 项的 JSON 字符串数组
  format: |-
    <charx_vars>{"可写键名": 新值}</charx_vars>
    <moonlight_choices>["行动一","行动二","行动三"]</moonlight_choices>
