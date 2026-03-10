require("fs").writeFileSync("assets/version.json", JSON.stringify({
  version: require("./package.json").version
}));
