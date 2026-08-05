# 夜路回声 · MyPost

黑暗、金属、哥特、奇幻风格的乐评存档站。

## 结构

```
MyPost/
├── *.md                    # 文章手稿（Markdown，放根目录即可被收录）
├── images/                 # 文章配图
├── scripts/build_site.py   # 静态站点生成器（Markdown → _site/）
├── .github/workflows/pages.yml  # GitHub Actions：push 即自动构建部署
└── _site/                  # 构建产物（已被 .gitignore 忽略）
```

## 发布新文章

1. 把新的 `.md` 文章放进仓库根目录，配图放 `images/`；
2. 提交并推送：

```bash
git add .
git commit -m "Add: 文章标题"
git push origin master
```

3. Actions 自动运行 `build_site.py` 并部署到 GitHub Pages，
   几分钟后访问 `https://trancer2thrash.github.io/MyPost/` 即可看到更新。

## 本地预览

```bash
pip install markdown pypinyin
python scripts/build_site.py
python -m http.server -d _site 8000
# 打开 http://127.0.0.1:8000
```

## 站点说明

- 站名、副标题、标语在 `scripts/build_site.py` 顶部的常量里，可自由修改；
- 文章日期取 git 首次提交时间；字数按「汉字逐字 + 英文按词」统计；
- slug 用拼音生成，中英文标题都能正确转成 URL。
