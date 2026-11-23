# 건축설계 법규 아카이브

제철플랜트 신설·증축·개축·합리화 건축 설계검토용 법규 정리 사이트입니다.

- 계획 → 설계 → 시공 → 사용승인 단계별 법규 체크리스트
- 내화구조·방화구획·피난 등 테마별 건축법 기준, 실시설계 기준
- 국가법령정보센터 현행 조문 바로가기
- 매일 아침 국가법령정보센터에서 법령 개정 여부를 자동 확인해 반영 (GitHub Actions)

체크 상태와 메모는 보는 사람의 브라우저에만 저장됩니다. 이 사이트는 참고용이며 법적 효력이 없습니다. 최종 판단은 현행 원문과 지자체 조례로 확인하세요.

---

## 처음 올리는 방법 (웹 브라우저만 사용)

1. **github.com** 에 로그인합니다 (계정이 없으면 가입).
2. 오른쪽 위 **+ → New repository**
   - Repository name: 예) `law-archive`
   - **Public** 선택, 나머지는 그대로 → **Create repository**
3. 만들어진 화면에서 **uploading an existing file** 링크를 누릅니다.
   - 이 폴더(`공개사이트`) 안의 **index.html, README.md, data 폴더, scripts 폴더**를 한꺼번에 끌어다 놓습니다.
   - 아래 **Commit changes** 클릭
4. 자동 갱신 설정 파일 만들기 (점으로 시작하는 폴더는 끌어다 놓기가 안 될 수 있어 직접 만듭니다)
   - 저장소 첫 화면 **Add file → Create new file**
   - 파일 이름 칸에 `.github/workflows/update.yml` 을 그대로 입력
   - 이 폴더의 `.github\workflows\update.yml` 을 메모장으로 열어 내용을 전부 복사해 붙여넣기 → **Commit changes**
5. 쓰기 권한 주기: **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save
6. 홈페이지 켜기: **Settings → Pages**
   - Source: **Deploy from a branch**, Branch: **main** / **(root)** → Save
   - 1~2분 뒤 위쪽에 주소가 나옵니다: `https://아이디.github.io/law-archive/`
7. 자동 갱신 시험: **Actions** 탭 → 왼쪽 **법령 개정 확인** → **Run workflow**
   - 초록 체크 ✔ 이면 성공. 이후 매일 07:30(한국시간)에 자동 실행됩니다.
   - 빨간 ✖ 이면 실행 기록을 열어 마지막 메시지를 확인하세요. 국가법령정보센터가 해외(GitHub) 서버 접속을 막으면 실패할 수 있습니다.

## 내용을 고칠 때

1. 체크리스트·테마 내용을 바꾼 뒤 PC에서 `웹페이지\공개사이트_만들기.ps1` 을 실행합니다.
2. 바뀐 파일(`index.html`, `data\items*.js`, `data\themes.js`, `data\manual.js`)만 GitHub에 다시 올립니다 (**Add file → Upload files**).
3. `data\status.js`, `data\status.json` 은 GitHub이 매일 갱신하는 파일이므로 다시 올리지 않습니다.

## 파일

| 파일 | 역할 |
|---|---|
| `index.html` | 홈페이지 화면 |
| `data/items.js`, `items_extra.js`, `manual.js` | 단계별 체크리스트 |
| `data/themes.js` | 테마별 법규 |
| `data/status.js`, `status.json` | 법령 시행일·공포일·개정 이력 (자동 갱신) |
| `data/extra_laws.txt` | 개정 확인에 추가할 법령 이름 |
| `scripts/check_updates.py` | 개정 확인 스크립트 |
| `.github/workflows/update.yml` | 매일 자동 실행 설정 |
