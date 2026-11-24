/*
  사이트 조정 4 (2026-11-24)
  - 화면에 보이는 '정정: 옛 …' / '메뉴얼 정정' 문구를 빼고 현행 근거만 표시
  - 원래 무엇을 고쳤는지는 261123_01·261124_01 정정목록 파일에 남아 있음
  - 모든 데이터 파일 다음에 실행
*/
(function(){
var RULES = [
  [/\s*—\s*정정:.*$/, ""],
  [/\s*\(메뉴얼 정정\)/g, ""],
  [/메뉴얼 정정:[^.]*\.\s*/g, ""],
  [/\s*—\s*메뉴얼의 '제38조'는 건축물대장 조항이므로 정정/g, ""],
  [/\s*—\s*메뉴얼의 '[^']*' 단서는 현행 시행령 제56조에 없음/g, ""],
  [/메뉴얼의 '[^']*'는 2022\.12 법 개편 전 조항\.\s*/g, ""],
  [/\s*메뉴얼의 '[^']*'은 옛 제도\./g, ""],
  [/\s*메뉴얼의 '[^']*'은 발주처 기준과 함께 다시 확인하세요\./g, ""]
];
function clean(s){ for (var i = 0; i < RULES.length; i++) s = s.replace(RULES[i][0], RULES[i][1]); return s; }
function walk(o, depth){
  if (!o || typeof o !== "object" || depth > 6) return;
  for (var k in o) {
    if (!Object.prototype.hasOwnProperty.call(o, k)) continue;
    if (typeof o[k] === "string") o[k] = clean(o[k]);
    else if (typeof o[k] === "object") walk(o[k], depth + 1);
  }
}
["LAW_ITEMS", "LAW_PATCH", "THEMES", "PERMIT", "PERMIT_ITEMS", "REVIEW_TABLE"].forEach(function(n){ walk(window[n], 0); });
})();
