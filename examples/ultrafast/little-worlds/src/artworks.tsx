export function Tidepool() {
  return <svg viewBox="0 0 300 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true" className="art-svg">
    <defs><pattern id="tide-grain" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".5" fill="#491c15" opacity=".13" /></pattern></defs>
    <rect width="300" height="320" fill="#eb8064" />
    <path d="M-40 243C29 290 94 246 66 190S63 82 131 63s168 0 133 99-48 138 62 147" fill="none" stroke="#933f37" strokeWidth="2" opacity=".45" />
    <path d="M-21 256C38 299 114 251 85 190S81 97 140 80s135-1 107 80-31 143 77 129" fill="none" stroke="#933f37" strokeWidth="2" opacity=".45" />
    <g transform="translate(151 160) rotate(-28)">
      <path d="M-52 80C-93 42-95-30-63-68C-37-99 4-87 20-64C39-102 87-72 85-38C83-15 64-4 47 4C99 6 98 59 68 74C39 89 18 67 7 53C9 100-30 105-52 80Z" fill="#273d36" />
      <path d="M-47 64C-68 36-68-10-52-40C-35-73-12-64-8-40C0-14-17 8-26 25C-6 5 17-4 27-23C41-54 68-34 48-10C36 6 9 18-4 23C18 14 57 19 54 37C51 52 19 38-7 31C5 50-10 73-25 66C-36 61-38 38-30 20" fill="none" stroke="#eaab84" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M-26 25Q-36 69-59 91" fill="none" stroke="#273d36" strokeWidth="8" strokeLinecap="round" />
    </g>
    <circle cx="240" cy="48" r="4" fill="#f9d4a3" /><text x="22" y="29" fill="#542d29" fontSize="8" letterSpacing="2">FIELD STUDY / 001</text>
    <text x="22" y="296" fill="#542d29" fontFamily="Georgia,serif" fontSize="17" fontStyle="italic">Look a little closer.</text><rect width="300" height="320" fill="url(#tide-grain)" />
  </svg>;
}

export function AfterHours() {
  return <svg viewBox="0 0 300 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true" className="art-svg">
    <defs><radialGradient id="record"><stop offset="0" stopColor="#172b65" /><stop offset="1" stopColor="#0a1744" /></radialGradient></defs>
    <rect width="300" height="320" fill="#233b92" />
    <text x="23" y="32" fill="#c6cdf6" fontSize="8" letterSpacing="2">FOR THE NIGHT OWLS</text>
    <circle cx="184" cy="167" r="142" fill="url(#record)" />
    {[63,70,77,84,91,98,105,112,119,126,133].map(r=><circle key={r} cx="184" cy="167" r={r} stroke="#6a79b5" opacity=".3" fill="none" strokeWidth=".7" />)}
    <circle cx="184" cy="167" r="51" fill="#f6ad5e" /><circle cx="184" cy="167" r="6" fill="#233b92" />
    <path d="M181 124v23m6-20v18" stroke="#ca663c" strokeWidth="2" /><text x="166" y="194" fill="#513520" fontSize="7" letterSpacing="1">SIDE A</text>
    <g transform="translate(25 83)" fill="#e0e6fd"><text fontFamily="Georgia,serif" fontSize="46" letterSpacing="-3"><tspan x="0" y="0">after</tspan><tspan x="0" y="45">hours</tspan></text></g>
    <path d="M25 271h26m-13-13v26" stroke="#f6ad5e" strokeWidth="1.5" /><text x="25" y="299" fill="#c6cdf6" fontSize="8" letterSpacing="2">LISTENING ROOM VOL. 02</text>
  </svg>;
}

export function SmallHours() {
  return <svg viewBox="0 0 300 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true" className="art-svg">
    <defs><linearGradient id="lamp" x1="0" x2="1"><stop stopColor="#78927a"/><stop offset=".5" stopColor="#b4c1a0"/><stop offset="1" stopColor="#5d7b67"/></linearGradient><linearGradient id="lampBase"><stop stopColor="#4d6957"/><stop offset=".5" stopColor="#82967a"/><stop offset="1" stopColor="#496851"/></linearGradient></defs>
    <rect width="300" height="320" fill="#e9e2bd" />
    <circle cx="235" cy="77" r="49" fill="#efeaca" />
    <path d="M0 240h300v80H0Z" fill="#d8cea6" /><ellipse cx="154" cy="258" rx="93" ry="15" fill="#ada17e" opacity=".28" />
    <path d="M133 158h34l14 84c0 15-62 15-62 0Z" fill="url(#lampBase)" />
    <ellipse cx="150" cy="243" rx="31" ry="8" fill="#5b755d" />
    <path d="M55 159C61 89 102 59 150 59s88 30 95 100Z" fill="url(#lamp)" />
    <ellipse cx="150" cy="159" rx="95" ry="19" fill="#445e4d" /><ellipse cx="150" cy="159" rx="78" ry="12" fill="#f1dfa7" />
    <path d="M75 137C89 91 111 76 133 70" fill="none" stroke="#cbd1b0" strokeWidth="2" opacity=".55" />
    <text x="23" y="32" fill="#626648" fontSize="8" letterSpacing="2">OBJECTS FOR SLOWER DAYS</text>
    <text x="23" y="298" fill="#575d43" fontFamily="Georgia,serif" fontSize="17" fontStyle="italic">Less, but lovelier.</text>
  </svg>;
}
