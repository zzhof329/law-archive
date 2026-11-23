/*
  사이트 조정 (2026-11-24) — 다른 데이터 파일 다음에 실행
  - 테마별 법규에서 '사내 설계기준' 제외
  - '인허가 서류·세움터' 설명에서 로그인 정보 관리 문구 제외
*/
(function(){
var TH = window.THEMES || [];
for (var i = TH.length - 1; i >= 0; i--) { if (TH[i].key === "sz") TH.splice(i, 1); }
for (var j = 0; j < TH.length; j++) {
  if (TH[j].key === "permit") TH[j].lead = "건축허가 접수 때 준비할 도서와 세움터 접수 순서입니다.";
}
})();
