# DOB backfill run status

run    30476002159  attempt 5
sha    0084a0781db1f33c4a3dfaa791ff54679aede854
when   2026-07-29T17:38:47Z

step outcomes (failure here is the whole point of this file):
  selftest  success
  before    success
  backfill  success
  after     success
  angles    success

coverage BEFORE:
  fighters: 1433/2678 with DOB  |  bouts with BOTH ages: 4223/8686 (48.6%)
coverage AFTER:
  fighters: 1433/2678 with DOB  |  bouts with BOTH ages: 4223/8686 (48.6%)

--- backfill tail (last 120 lines) ---
missing DOB for 1245 of 2678 fighters
BEFORE: fighters: 1433/2678 with DOB  |  bouts with BOTH ages: 4223/8686 (48.6%)
ufcstats pass
  warmed cookie jar: 2994 chars, 0 cookie(s) held
  index 'a' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
    ---- full challenge body ----
<!doctype html><html><head><meta charset="utf-8">
<title>Loading…</title><meta name="robots" content="noindex">
<style>body{font-family:sans-serif;color:#666;text-align:center;margin-top:25vh}</style>
</head><body>
<p>Checking your browser…</p>
<noscript>This site requires JavaScript.</noscript>
<script>
(function(){
var K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
function ror(x,n){return (x>>>n)|(x<<(32-n));}
function sha256(msg){
  var bytes=[];for(var i=0;i<msg.length;i++){
    var c=msg.charCodeAt(i);
    if(c<128){bytes.push(c);}
    else if(c<2048){bytes.push(192|(c>>6),128|(c&63));}
    else{bytes.push(224|(c>>12),128|((c>>6)&63),128|(c&63));}
  }
  var l=bytes.length;bytes.push(0x80);
  while((bytes.length%64)!==56)bytes.push(0);
  var bl=l*8;
  bytes.push(0,0,0,0,(bl>>>24)&255,(bl>>>16)&255,(bl>>>8)&255,bl&255);
  var H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  for(var o=0;o<bytes.length;o+=64){
    var W=new Array(64);
    for(var t=0;t<16;t++){W[t]=(bytes[o+t*4]<<24)|(bytes[o+t*4+1]<<16)|(bytes[o+t*4+2]<<8)|bytes[o+t*4+3];}
    for(t=16;t<64;t++){
      var s0=ror(W[t-15],7)^ror(W[t-15],18)^(W[t-15]>>>3);
      var s1=ror(W[t-2],17)^ror(W[t-2],19)^(W[t-2]>>>10);
      W[t]=(W[t-16]+s0+W[t-7]+s1)|0;
    }
    var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
    for(t=0;t<64;t++){
      var S1=ror(e,6)^ror(e,11)^ror(e,25);
      var ch=(e&f)^(~e&g);
      var T1=(h+S1+ch+K[t]+W[t])|0;
      var S0=ror(a,2)^ror(a,13)^ror(a,22);
      var mj=(a&b)^(a&c)^(b&c);
      var T2=(S0+mj)|0;
      h=g;g=f;f=e;e=(d+T1)|0;d=c;c=b;b=a;a=(T1+T2)|0;
    }
    H[0]=(H[0]+a)|0;H[1]=(H[1]+b)|0;H[2]=(H[2]+c)|0;H[3]=(H[3]+d)|0;
    H[4]=(H[4]+e)|0;H[5]=(H[5]+f)|0;H[6]=(H[6]+g)|0;H[7]=(H[7]+h)|0;
  }
  var out='';
  for(i=0;i<8;i++){out+=('00000000'+(H[i]>>>0).toString(16)).slice(-8);}
  return out;
}
var nonce="d9f53d6f8779abb7",
    target=new Array(2+1).join('0');
var n=0;
while(sha256(nonce+':'+n).slice(0,target.length)!==target){n++;}
var xhr=new XMLHttpRequest();
xhr.open('POST',"/__c",true);
xhr.setRequestHeader('Content-Type','application/x-www-form-urlencoded');
xhr.onload=function(){if(xhr.status>=200&&xhr.status<300)location.reload();};
xhr.send('nonce='+encodeURIComponent(nonce)+'&n='+n);
})();
</script>
</body></html>

    ---- end body ----
  index 'b' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'c' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'd' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'e' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'f' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'g' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'h' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'i' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'j' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'k' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'l' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'm' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'n' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'o' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'p' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'q' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'r' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 's' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 't' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'u' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'v' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'w' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'x' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'y' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  index 'z' parsed 0 rows from 2994 chars, 0 'fighter-details' mentions, challenge=True
  ufcstats index: 0 fighters enumerated
  0 of them are names we are missing — fetching details
  ufcstats filled 0 DOBs, 0 stances
wikidata rows: 20686 unambiguous fighter names
ESPN search pass over 300 remaining names
  ...100/300  espn hits 0
  ...200/300  espn hits 0
  ...300/300  espn hits 0
added: ufcstats 0  wikidata 0  espn 0  stances 0  rejected as implausible 3
AFTER:  fighters: 1433/2678 with DOB  |  bouts with BOTH ages: 4223/8686 (48.6%)

--- angles tail (last 40 lines) ---
::warning::age join weak (4223/8686) — the baseline is not properly age-adjusted; treat wins as unproven
========================================================================
UFC ANGLES 2 — wear and tear beyond chin
baseline already contains Elo + CHIN + AGE (both shipped/validated)
========================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)  both-DOB known: 4223 (49%)

--- FULL SAMPLE (age term diluted: it is 0 wherever a DOB is missing)
baseline (Elo + chin + age): a=1.6 c=-0.06 g=-0.06  TRAIN LL -0.67202
baseline HOLDOUT -0.65011 (n=1771)
KDABS   knockdowns absorbed  b= -0.03  train_win=True   holdout dLL +0.00114  periods 3/3  -> ROBUST WIN
MILEAGE career hours fought  b= -0.05  train_win=False  holdout dLL +0.00208  periods 3/3  -> win, not robust
ABSORB  sig absorbed / min   b= -0.18  train_win=True   holdout dLL +0.00380  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=  0.05  train_win=True   holdout dLL -0.00019  periods 1/3  -> NULL

--- AGE-COMPLETE SUBSET (n=4223) — the decisive test
baseline (Elo + chin + age): a=1.6 c=-0.12 g=-0.06  TRAIN LL -0.66698
baseline HOLDOUT -0.64830 (n=1491)
KDABS   knockdowns absorbed  b= -0.03  train_win=True   holdout dLL +0.00015  periods 1/3  -> win, not robust
MILEAGE career hours fought  b= -0.05  train_win=False  holdout dLL +0.00137  periods 2/3  -> win, not robust
ABSORB  sig absorbed / min   b=  -0.1  train_win=True   holdout dLL +0.00137  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=   0.1  train_win=True   holdout dLL -0.00063  periods 1/3  -> NULL

Ship rule: ROBUST WIN on the AGE-COMPLETE subset. An angle that wins
only on the full sample is most likely re-discovering age.
verdict -> ../experiments/UFC-ANGLES2-VERDICT-WIDENED.md
