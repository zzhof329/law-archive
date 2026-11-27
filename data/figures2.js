/*
  새 테마 도식 (2026-11-27) — 건설안전·안전관리비 / 발주·계약·용역 / 경관·고도·입지
  - 자주찾는법규.js 다음에 실행. 색은 페이지 .fg CSS
*/
(function(){
function T(x, y, s, cls, a){ return '<text x="'+x+'" y="'+y+'"'+(cls?' class="'+cls+'"':'')+(a?' text-anchor="'+a+'"':'')+'>'+s+'</text>'; }
function Rc(x, y, w, h, cls, rx){ return '<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" rx="'+(rx==null?6:rx)+'" class="'+cls+'"/>'; }
function Ln(x1, y1, x2, y2, cls, mk){ return '<line x1="'+x1+'" y1="'+y1+'" x2="'+x2+'" y2="'+y2+'" class="'+(cls||'ln')+'"'+(mk?' marker-end="url(#'+mk+')"':'')+'/>'; }
function B(x, y, w, h, cls, lines, tc){ var s = Rc(x, y, w, h, cls), n = lines.length, y0 = y + h/2 - (n-1)*9 + 5; for (var i = 0; i < n; i++) s += T(x + w/2, y0 + i*18, lines[i], (i ? 's' : 'b') + (tc ? ' ' + tc : ''), 'middle'); return s; }
function SVG(id, h, label, body){ return '<svg class="fg" viewBox="0 0 480 '+h+'" role="img" aria-label="'+label+'"><defs><marker id="'+id+'" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10z" class="mk"/></marker></defs>' + body + '</svg>'; }
var F = {};

F.safety = { cap:"공사금액에 따른 주요 안전 의무", svg: SVG("mk-sf", 214, "공사금액별 안전 의무",
  T(10,22,"공사금액에 따른 안전 의무 (산업안전보건법)","b")
  + Ln(130,70,470,70,"ln2","mk-sf")
  + Ln(160,64,160,76,"ln") + Ln(280,64,280,76,"ln") + Ln(400,64,400,76,"ln")
  + T(160,56,"1억","b","middle") + T(280,56,"50억","b","middle") + T(400,56,"120억","b","middle") + T(400,92,"(토목 150억)","s","middle")
  + T(10,122,"기술지도계약","s") + Rc(160,108,240,22,"acb",4) + T(280,124,"1억 이상 ~ 120억 미만","s","middle")
  + T(10,154,"안전관리자 선임","s") + Rc(280,140,190,22,"box2",4) + T(375,156,"50억 이상","s","middle")
  + T(10,186,"안전관리자 전담","s") + Rc(400,172,70,22,"stb",4) + T(435,188,"120억↑","s w","middle")
  + T(10,208,"1억 미만이라도 건축허가 대상 공사는 기술지도계약 대상","s act")
)};

F.contract = { cap:"분리발주·분리도급 원칙", svg: SVG("mk-ct", 220, "분리발주 원칙",
  B(140,10,200,40,"stb",["제철소 공사 발주"],"w")
  + Ln(240,50,240,70) + Ln(64,70,418,70)
  + Ln(64,70,64,96,"ln","mk-ct") + Ln(182,70,182,96,"ln","mk-ct") + Ln(300,70,300,96,"ln","mk-ct") + Ln(418,70,418,96,"ln","mk-ct")
  + B(10,98,108,58,"box",["건축·토목","건설산업기본법"])
  + B(128,98,108,58,"acb",["전기","전기공사업법 §11"])
  + B(246,98,108,58,"acb",["정보통신","공사업법 §25"])
  + B(364,98,108,58,"acb",["소방","공사업법 §21"])
  + T(10,186,"주황 칸은 다른 업종 공사와 분리해 발주·도급하는 것이 원칙","s")
  + T(10,206,"전기 예외: 가설 전기, 10kW 이하(민간), 발전소 주설비, 턴키·대안 입찰 등","s")
)};

F.location = { cap:"높이·경관 제한 개념도", svg: SVG("mk-lc", 286, "비행안전구역과 항공장애 표시",
  Ln(10,230,470,230,"ln2")
  + Rc(30,190,130,40,"box2",2) + T(95,215,"공장동","s","middle")
  + '<polygon points="200,230 226,230 222,72 204,72" class="obj"/>' + '<circle cx="213" cy="66" r="6" class="acf"/>'
  + T(236,70,"60m 이상 → 항공장애 표시등","s act")
  + Ln(10,176,470,36,"path")
  + T(236,140,"비행안전구역 높이 제한면(구역별)","s")
  + T(236,160,"넘으면 설치 제한 → 관할 부대 협의","s")
  + Rc(330,170,120,60,"acb",3) + T(390,196,"외관·색채","b","middle") + T(390,214,"경관 협의","s","middle")
  + T(10,256,"광양 산업단지: 연면적 5천~1만㎡ 경관자문, 1만㎡ 이상 경관심의","s")
  + T(10,276,"굴뚝·집진탑·타워는 계획 초기에 높이 제한부터 확인","s")
)};

var TH = window.THEMES || [];
for (var i = 0; i < TH.length; i++) if (F[TH[i].key]) TH[i].fig = F[TH[i].key];
})();
