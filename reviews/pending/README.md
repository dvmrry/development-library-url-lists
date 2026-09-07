# Pending package-endpoint review

257 candidates. Suggestions only; no command below has been executed.

Confidence describes package evidence, not whether a whole-host block is appropriate. Check the evidence, public availability, and shared-host impact before promoting. Observed repository paths are scope clues, not automatically approved path rules.

## Ecosystem coverage

| Ecosystem | Pending |
| --- | ---: |
| containers | 14 |
| cpp | 11 |
| dart | 2 |
| dotnet | 5 |
| erlang | 2 |
| go | 2 |
| javascript | 13 |
| julia | 3 |
| jvm | 64 |
| multi_ecosystem | 24 |
| php | 5 |
| python | 23 |
| r | 86 |
| ruby | 2 |
| rust | 3 |
| swift | 4 |

## Suggested next batch

Up to 20 targets, balanced across ecosystems; within each ecosystem, confidence and distinct-owner reach set the order. Multi-category targets appear once.

### mirror.gcr.io

- Ecosystems: containers; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 2 owners / 2 repositories / 2 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/coder/coder/blob/4875ae218a402b8350c7315b8d08a7393f8d08f5/dogfood/coder/ubuntu-22.04/files/etc/docker/daemon.json>)
- [Evidence 2](<https://github.com/coder/coder/blob/4875ae218a402b8350c7315b8d08a7393f8d08f5/dogfood/coder/ubuntu-26.04/files/etc/docker/daemon.json>)
- [Evidence 3](<https://github.com/play-with-docker/play-with-docker/blob/62cb0727cab93cf4273017d33e965a5f26c83b05/dockerfiles/dind/daemon.json>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py mirror.gcr.io --category containers --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py mirror.gcr.io --reason 'REPLACE with rejection rationale'
```

### artifactory-local.silabs.net

- Ecosystems: cpp; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 1 owners / 2 repositories / 2 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/SiliconLabs/matter_extension/blob/5e1a67e5bc22b0778a4e8844f4d08b4d77a2d78b/packages/remotes.json>)
- [Evidence 2](<https://github.com/SiliconLabs/z-wave-ts-silabs/blob/10c51c790f463d0bee11eb7fe3d30bb33afcfe26/remotes.json>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py artifactory-local.silabs.net --category cpp --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py artifactory-local.silabs.net --reason 'REPLACE with rejection rationale'
```

### dart-pub.mirrors.sjtug.sjtu.edu.cn

- Ecosystems: dart; evidence confidence: low.
- Review: new-target; flags: non-configuration-evidence-only.
- Code reach: 1 owners / 1 repositories / 1 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/yuchuangu85/Develop-Source/blob/0868142a7b4994194e4980c4620ae6ee628a3bfb/Cross-Platform/Flutter/README.md>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py dart-pub.mirrors.sjtug.sjtu.edu.cn --category dart --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py dart-pub.mirrors.sjtug.sjtu.edu.cn --reason 'REPLACE with rejection rationale'
```

### ci.appveyor.com

- Ecosystems: dotnet; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 3 owners / 5 repositories / 5 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/CosmosOS/Cosmos/blob/764ceb0d5697024f35fe4ae9cae9f2f0d3662610/Build/Targets/RestoreSources.props>)
- [Evidence 2](<https://github.com/CosmosOS/IL2CPU/blob/a48ad6552b136c6290b1e6c88ad157070b0ce9da/build/Targets/RestoreSources.props>)
- [Evidence 3](<https://github.com/CosmosOS/XSharp/blob/a7dd07032aa75740be0163ba0b7f5d8456413fc4/build/Targets/RestoreSources.props>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py ci.appveyor.com --category dotnet --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py ci.appveyor.com --reason 'REPLACE with rejection rationale'
```

### hexpm.upyun.com

- Ecosystems: erlang; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 9 owners / 10 repositories / 10 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/DogLooksGood/dotfiles/blob/1ffc24b68cc5d82446bcebfda59861061ddae7cc/manjaro-dots/.zshrc>)
- [Evidence 2](<https://github.com/EdmondFrank/gitgud/blob/6b51e00001aed397fe0eebb7ace96597ffb14c8e/Dockerfile>)
- [Evidence 3](<https://github.com/damon-kwok/oh-my-env/blob/ad763ed14832948dcaae91b0218bfc3596d90fdb/packages/lang/elixir>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py hexpm.upyun.com --category erlang --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py hexpm.upyun.com --reason 'REPLACE with rejection rationale'
```

### athens.azurefd.net

- Ecosystems: go; evidence confidence: low.
- Review: new-target; flags: non-configuration-evidence-only.
- Code reach: 1 owners / 1 repositories / 1 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/IBAX-io/go-ibax/blob/66f135846a10d1a1edddbceff517b9c937639576/README.md>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py athens.azurefd.net --category go --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py athens.azurefd.net --reason 'REPLACE with rejection rationale'
```

### npm.jsr.io

- Ecosystems: javascript; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 5 owners / 6 repositories / 6 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/OpenNeuroOrg/openneuro/blob/273c0f697a505c4dc5dc2d2c33f42a4eae9ea6ab/.yarnrc.yml>)
- [Evidence 2](<https://github.com/launchdarkly/js-core/blob/ecb0c6231bfabdbdd9b4b0be484a7bc50172ed45/.yarnrc.yml>)
- [Evidence 3](<https://github.com/mlx-node/mlx-node/blob/ddd16ad344594bda7ce97983320c05056cc864fb/.yarnrc.yml>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py npm.jsr.io --category javascript --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py npm.jsr.io --reason 'REPLACE with rejection rationale'
```

### juliahub.com

- Ecosystems: julia; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 1 owners / 1 repositories / 1 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/DyadLang/SpacePowerWorkshop.jl/blob/7742ccc052efccf17cdc34bdee444071b4348f1e/README.md>)
- [Evidence 2](<https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py juliahub.com --category julia --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py juliahub.com --reason 'REPLACE with rejection rationale'
```

### hub.spigotmc.org

- Ecosystems: jvm; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 3 owners / 3 repositories / 3 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/Hex27/TerraformGenerator/blob/7e280aa78079697c8d774f3741270f2f9b5f676e/build.gradle.kts>)
- [Evidence 2](<https://github.com/PlaceholderAPI/PlaceholderAPI/blob/7d21d2f1d73f045b86812c70e6c6975b102c6d89/build.gradle.kts>)
- [Evidence 3](<https://github.com/pop4959/LWCX/blob/3cb6ce9f2a75261ebef40fada026b88539c88c95/build.gradle.kts>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py hub.spigotmc.org --category jvm --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py hub.spigotmc.org --reason 'REPLACE with rejection rationale'
```

### mirror.lzu.edu.cn

- Ecosystems: multi_ecosystem, r; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 0 owners / 0 repositories / 0 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://cran.r-project.org/CRAN_mirrors.csv>)
- [Evidence 2](<https://mirrors.cernet.edu.cn/api/scoring>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py mirror.lzu.edu.cn --category multi_ecosystem --category r --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py mirror.lzu.edu.cn --reason 'REPLACE with rejection rationale'
```

### plugins.roundcube.net

- Ecosystems: php; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 3 owners / 3 repositories / 3 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/alexandregz/twofactor_gauthenticator/blob/b14306150da37c18b7a1e761875e8aa06d47e6a0/composer.json>)
- [Evidence 2](<https://github.com/sentora/sentora-core/blob/78e4041bfb981868dcfbebff47d1a991a09f3ca1/etc/apps/webmail/composer.json-dist>)
- [Evidence 3](<https://github.com/zpanel/zpanelx/blob/f9e8d4d9a281b382292985f09056d97694c3258e/etc/apps/webmail/composer.json-dist>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py plugins.roundcube.net --category php --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py plugins.roundcube.net --reason 'REPLACE with rejection rationale'
```

### pypi.python.org

- Ecosystems: python; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 8 owners / 8 repositories / 10 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/ATOMScience-org/AMPL/blob/c3fff25f138fcc792a62cad053e6d2707146f240/pip/cuda_requirements.txt>)
- [Evidence 2](<https://github.com/ATOMScience-org/AMPL/blob/c3fff25f138fcc792a62cad053e6d2707146f240/pip/docker_requirements.txt>)
- [Evidence 3](<https://github.com/ATOMScience-org/AMPL/blob/c3fff25f138fcc792a62cad053e6d2707146f240/pip/mchip_requirements.txt>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py pypi.python.org --category python --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py pypi.python.org --reason 'REPLACE with rejection rationale'
```

### cran.rstudio.com

- Ecosystems: r; evidence confidence: high.
- Review: new-target; flags: none.
- Code reach: 3 owners / 3 repositories / 3 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/Kaggle/docker-rstats/blob/7f87ef40939e893f34939e3f033c61cd2d1ce9bb/RProfile.R>)
- [Evidence 2](<https://github.com/natverse/nat/blob/ccf69b118f3475130748bafb1b087c8aca30a6ce/build_docs.r>)
- [Evidence 3](<https://github.com/rstudio/tinytex/blob/d01200eb642187eb3b00b02084500844906cbeef/tools/config.R>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py cran.rstudio.com --category r --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py cran.rstudio.com --reason 'REPLACE with rejection rationale'
```

### gem.coop

- Ecosystems: ruby; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 0 owners / 0 repositories / 0 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py gem.coop --category ruby --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py gem.coop --reason 'REPLACE with rejection rationale'
```

### crates.sunscreen.tech

- Ecosystems: rust; evidence confidence: low.
- Review: new-target; flags: none.
- Code reach: 1 owners / 1 repositories / 1 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/Sunscreen-tech/Sunscreen/blob/f8ee4a0dc32418f2acd9e176c6f0af73cdf68d40/.cargo/config.toml>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py crates.sunscreen.tech --category rust --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py crates.sunscreen.tech --reason 'REPLACE with rejection rationale'
```

### cocoapods.org

- Ecosystems: swift; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 0 owners / 0 repositories / 0 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py cocoapods.org --category swift --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py cocoapods.org --reason 'REPLACE with rejection rationale'
```

### artifacthub.io

- Ecosystems: containers; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 0 owners / 0 repositories / 0 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py artifacthub.io --category containers --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py artifacthub.io --reason 'REPLACE with rejection rationale'
```

### artifactory.silabs.net

- Ecosystems: cpp; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 1 owners / 2 repositories / 2 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/SiliconLabs/matter_extension/blob/5e1a67e5bc22b0778a4e8844f4d08b4d77a2d78b/packages/remotes.json>)
- [Evidence 2](<https://github.com/SiliconLabs/z-wave-ts-silabs/blob/10c51c790f463d0bee11eb7fe3d30bb33afcfe26/remotes.json>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py artifactory.silabs.net --category cpp --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py artifactory.silabs.net --reason 'REPLACE with rejection rationale'
```

### mirrors.cnnic.cn

- Ecosystems: dart; evidence confidence: low.
- Review: new-target; flags: non-configuration-evidence-only.
- Code reach: 1 owners / 1 repositories / 1 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/yuchuangu85/Develop-Source/blob/0868142a7b4994194e4980c4620ae6ee628a3bfb/Cross-Platform/Flutter/README.md>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py mirrors.cnnic.cn --category dart --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py mirrors.cnnic.cn --reason 'REPLACE with rejection rationale'
```

### devdiv.pkgs.visualstudio.com

- Ecosystems: dotnet, python; evidence confidence: medium.
- Review: new-target; flags: none.
- Code reach: 2 owners / 2 repositories / 4 content hashes.
- Observed repository targets: unavailable in older evidence; inspect the configuration before choosing host/path scope.
- [Evidence 1](<https://github.com/X-Sharp/XSharpPublic/blob/4e7027e2b5fbc1cbb4656ae4e7398617a89913d6/src/Compiler/eng/InternalTools.props>)
- [Evidence 2](<https://github.com/X-Sharp/XSharpPublic/blob/4e7027e2b5fbc1cbb4656ae4e7398617a89913d6/src/Compiler/eng/common/internal/Tools.csproj>)
- [Evidence 3](<https://github.com/X-Sharp/XSharpPublic/blob/4e7027e2b5fbc1cbb4656ae4e7398617a89913d6/src/Roslyn/eng/InternalTools.props>)

After inspecting evidence and scope, choose a decision:

```sh
python scripts/promote.py devdiv.pkgs.visualstudio.com --category dotnet --category python --review-note 'REPLACE with scope and evidence review'
```

Or reject:

```sh
python scripts/reject.py devdiv.pkgs.visualstudio.com --reason 'REPLACE with rejection rationale'
```

## Full queue

| Target | Ecosystems | Confidence | Owners | Review flags |
| --- | --- | --- | ---: | --- |
| hexpm.upyun.com | erlang | high | 9 |  |
| pypi.python.org | python | high | 8 |  |
| npm.jsr.io | javascript | high | 5 |  |
| registry.npm.taobao.org | javascript | high | 4 |  |
| ci.appveyor.com | dotnet | high | 3 |  |
| cran.rstudio.com | r | high | 3 |  |
| hub.spigotmc.org | jvm | high | 3 |  |
| plugins.roundcube.net | php | high | 3 |  |
| maven.wso2.org | jvm | high | 1 |  |
| archive.linux.duke.edu | r | high | 0 |  |
| brieger.esalq.usp.br | r | high | 0 |  |
| cran-r.c3sl.ufpr.br | r | high | 0 |  |
| cran.030-datenrettung.de | r | high | 0 |  |
| cran.asia | r | high | 0 |  |
| cran.asnr.fr | r | high | 0 |  |
| cran.case.edu | r | high | 0 |  |
| cran.csie.ntu.edu.tw | r | high | 0 |  |
| cran.csiro.au | r | high | 0 |  |
| cran.datenrettung360.de | r | high | 0 |  |
| cran.dcc.uchile.cl | r | high | 0 |  |
| cran.hafro.is | r | high | 0 |  |
| cran.isid.ac.in | r | high | 0 |  |
| cran.itam.mx | r | high | 0 |  |
| cran.ma.imperial.ac.uk | r | high | 0 |  |
| cran.mi2.ai | r | high | 0 |  |
| cran.mirror.garr.it | r | high | 0 |  |
| cran.mirror.rafal.ca | r | high | 0 |  |
| cran.mirrors.hoobly.com | r | high | 0 |  |
| cran.ms.unimelb.edu.au | r | high | 0 |  |
| cran.nyuad.nyu.edu | r | high | 0 |  |
| cran.r-project.hu | r | high | 0 |  |
| cran.radicaldevelop.com | r | high | 0 |  |
| cran.rediris.es | r | high | 0 |  |
| cran.stat.auckland.ac.nz | r | high | 0 |  |
| cran.stat.unipd.it | r | high | 0 |  |
| cran.uib.no | r | high | 0 |  |
| cran.um.ac.ir | r | high | 0 |  |
| cran.uni-muenster.de | r | high | 0 |  |
| cran.usk.ac.id | r | high | 0 |  |
| cran.wu.ac.at | r | high | 0 |  |
| cran.wustl.edu | r | high | 0 |  |
| espejito.fder.edu.uy | r | high | 0 |  |
| ftp.belnet.be | r | high | 0 |  |
| ftp.cc.uoc.gr | r | high | 0 |  |
| ftp.cixug.es | r | high | 0 |  |
| ftp.fau.de | r | high | 0 |  |
| ftp.gwdg.de | r | high | 0 |  |
| ftp.osuosl.org | r | high | 0 |  |
| ftp.uni-sofia.bg | r | high | 0 |  |
| ftp.ussg.iu.edu | r | high | 0 |  |
| ftp.yz.yamagata-u.ac.jp | r | high | 0 |  |
| lib.stat.cmu.edu | r | high | 0 |  |
| mirror-hk.koddos.net | r | high | 0 |  |
| mirror.aarnet.edu.au | r | high | 0 |  |
| mirror.accum.se | r | high | 0 |  |
| mirror.cedia.org.ec | r | high | 0 |  |
| mirror.chpc.utah.edu | r | high | 0 |  |
| mirror.clientvps.com | r | high | 0 |  |
| mirror.csclub.uwaterloo.ca | r | high | 0 |  |
| mirror.dogado.de | r | high | 0 |  |
| mirror.fcaglp.unlp.edu.ar | r | high | 0 |  |
| mirror.ibcp.fr | r | high | 0 |  |
| mirror.its.umich.edu | r | high | 0 |  |
| mirror.kamp.de | r | high | 0 |  |
| mirror.las.iastate.edu | r | high | 0 |  |
| mirror.library.ucy.ac.cy | r | high | 0 |  |
| mirror.lyrahosting.com | r | high | 0 |  |
| mirror.lzu.edu.cn | multi_ecosystem, r | high | 0 |  |
| mirror.maeen.sa | r | high | 0 |  |
| mirror.marwan.ma | r | high | 0 |  |
| mirror.metanet.ch | r | high | 0 |  |
| mirror.niser.ac.in | r | high | 0 |  |
| mirror.rabisu.com | r | high | 0 |  |
| mirror.truenetwork.ru | r | high | 0 |  |
| mirror.uned.ac.cr | r | high | 0 |  |
| mirrors.cicku.me | r | high | 0 |  |
| mirrors.cqu.edu.cn | r | high | 0 |  |
| mirrors.dotsrc.org | r | high | 0 |  |
| mirrors.hust.edu.cn | r | high | 0 |  |
| mirrors.nics.utk.edu | r | high | 0 |  |
| mirrors.nwafu.edu.cn | r | high | 0 |  |
| mirrors.qlu.edu.cn | multi_ecosystem, r | high | 0 |  |
| mirrors.sjtug.sjtu.edu.cn | r | high | 0 |  |
| mirrors.sustech.edu.cn | multi_ecosystem, r | high | 0 |  |
| mirrors.xjtu.edu.cn | multi_ecosystem, r | high | 0 |  |
| mirrors.zju.edu.cn | r | high | 0 |  |
| muug.ca | r | high | 0 |  |
| pbil.univ-lyon1.fr | r | high | 0 |  |
| stat.ethz.ch | r | high | 0 |  |
| vps.fmvz.usp.br | r | high | 0 |  |
| www.freestatistics.org | r | high | 0 |  |
| www.stats.bris.ac.uk | r | high | 0 |  |
| cache-redirector.jetbrains.com | jvm | medium | 2 |  |
| devdiv.pkgs.visualstudio.com | dotnet, python | medium | 2 |  |
| maven.vaadin.com | jvm | medium | 2 |  |
| mirror.gcr.io | containers | medium | 2 |  |
| npm.fontawesome.com | javascript | medium | 2 |  |
| nuget.org | dotnet | medium | 2 |  |
| packagemanager.rstudio.com | r | medium | 2 |  |
| repo.codemc.io | jvm | medium | 2 |  |
| repo.papermc.io | jvm | medium | 2 |  |
| artifactory-local.silabs.net | cpp | medium | 1 |  |
| artifactory.silabs.net | cpp | medium | 1 |  |
| artifacts.elastic.co | jvm | medium | 1 |  |
| conan.silabs.net | cpp | medium | 1 |  |
| juliahub.com | julia | medium | 1 |  |
| anaconda.org | python | medium | 0 |  |
| artifacthub.io | containers | medium | 0 |  |
| artifacts.alfresco.com | jvm | medium | 0 |  |
| bower.io | javascript | medium | 0 |  |
| build.shibboleth.net | jvm | medium | 0 |  |
| cocoapods.org | swift | medium | 0 |  |
| conan.io | cpp | medium | 0 |  |
| conda-forge.org | python | medium | 0 |  |
| ctan.org | multi_ecosystem | medium | 0 |  |
| elpa.gnu.org | multi_ecosystem | medium | 0 |  |
| elpa.nongnu.org | multi_ecosystem | medium | 0 |  |
| forge.puppet.com | multi_ecosystem | medium | 0 |  |
| gem.coop | ruby | medium | 0 |  |
| metacpan.org | multi_ecosystem | medium | 0 |  |
| mirror.bjtu.edu.cn | multi_ecosystem | medium | 0 |  |
| mirror.nyist.edu.cn | multi_ecosystem | medium | 0 |  |
| mirror.sysu.edu.cn | multi_ecosystem | medium | 0 |  |
| mirrors.hit.edu.cn | multi_ecosystem | medium | 0 |  |
| mirrors.jcut.edu.cn | multi_ecosystem | medium | 0 |  |
| mirrors.jlu.edu.cn | multi_ecosystem | medium | 0 |  |
| mirrors.sdu.edu.cn | multi_ecosystem | medium | 0 |  |
| mirrors.wsyu.edu.cn | multi_ecosystem | medium | 0 |  |
| nexus.gael.cloud | jvm | medium | 0 |  |
| open-vsx.org | multi_ecosystem | medium | 0 |  |
| package.elm-lang.org | multi_ecosystem | medium | 0 |  |
| packages.spack.io | multi_ecosystem | medium | 0 |  |
| pkgs.racket-lang.org | multi_ecosystem | medium | 0 |  |
| registry.bazel.build | multi_ecosystem | medium | 0 |  |
| registry.terraform.io | multi_ecosystem | medium | 0 |  |
| repo.jenkins-ci.org | jvm | medium | 0 |  |
| repository.cloudera.com | jvm | medium | 0 |  |
| reservoir.lean-lang.org | multi_ecosystem | medium | 0 |  |
| swiftpackageindex.com | swift | medium | 0 |  |
| vcpkg.io | cpp | medium | 0 |  |
| api.bintray.com | cpp | low | 11 | retired-service |
| dl.bintray.com | jvm | low | 5 | retired-service |
| jcenter.bintray.com | jvm | low | 4 | retired-service |
| docker.mirrors.ustc.edu.cn | containers | low | 2 |  |
| 120.25.164.233:8081 | jvm | low | 1 | nonstandard-port |
| aiinfra.pkgs.visualstudio.com | python | low | 1 |  |
| alpine-wheels.github.io | python | low | 1 |  |
| anaconda.mgb.org | python | low | 1 |  |
| anaconda.rdhpcs.noaa.gov | python | low | 1 |  |
| api.modrinth.com | jvm | low | 1 |  |
| artifactory.audeering.com | python | low | 1 | non-configuration-evidence-only |
| artifactory.jpl.nasa.gov | python | low | 1 |  |
| artifactory.onefact.net | cpp | low | 1 |  |
| artifactory.predix.io | jvm | low | 1 | non-configuration-evidence-only |
| artifacts.camunda.com | jvm | low | 1 |  |
| athens.azurefd.net | go | low | 1 | non-configuration-evidence-only |
| autoincrement-versions-maven-plugin.googlecode.com | jvm | low | 1 |  |
| buf.build | javascript | low | 1 |  |
| cfmlprojects.org | jvm | low | 1 |  |
| ci.ender.zone | jvm | low | 1 |  |
| code.mmk.pw | python | low | 1 |  |
| conan.iteale.com:19479 | cpp | low | 1 | nonstandard-port |
| crates.sunscreen.tech | rust | low | 1 |  |
| dart-pub.mirrors.sjtug.sjtu.edu.cn | dart | low | 1 | non-configuration-evidence-only |
| data.dgl.ai | python | low | 1 |  |
| data.pyg.org | python | low | 1 |  |
| docker.1ms.run | containers | low | 1 |  |
| docker.1panel.live | containers | low | 1 |  |
| docker.amingg.com | containers | low | 1 |  |
| dotnetfeed.blob.core.windows.net | dotnet | low | 1 |  |
| dx5z2hy7.mirror.aliyuncs.com | containers | low | 1 |  |
| elliot-braem-1032-near-social-js-ui-near-social-j-6efa4bd9f-ze.zephyrcloud.app | cpp | low | 1 | non-configuration-evidence-only |
| git.amazingcat.net | javascript | low | 1 |  |
| git.gem.cache.pangea.pub | ruby | low | 1 |  |
| git.psi.ch | cpp | low | 1 |  |
| gitlab.protontech.ch | javascript | low | 1 |  |
| hdi5v8p1.mirror.aliyuncs.com | containers | low | 1 |  |
| hub-mirror.c.163.com | containers | low | 1 |  |
| hub.rat.dev | containers | low | 1 |  |
| hub1.nat.tf | containers | low | 1 |  |
| internal-artifacts.deltares.nl | cpp | low | 1 |  |
| jaspersoft.artifactoryonline.com | jvm | low | 1 |  |
| jfrog.booking.com | python | low | 1 |  |
| jogamp.org | jvm | low | 1 |  |
| libraries.minecraft.net | jvm | low | 1 |  |
| masa.dy.fi | jvm | low | 1 |  |
| maven.aksw.org | jvm | low | 1 |  |
| maven.enginehub.org | jvm | low | 1 |  |
| maven.fabric.io | jvm | low | 1 |  |
| maven.fabricmc.net | jvm | low | 1 |  |
| maven.in.devexperts.com | jvm | low | 1 |  |
| maven.jamieswhiteshirt.com | jvm | low | 1 |  |
| maven.java.net | jvm | low | 1 |  |
| maven.opennms.org | jvm | low | 1 |  |
| maven.parchmentmc.org | jvm | low | 1 |  |
| maven.repository.redhat.com | jvm | low | 1 |  |
| maven.restlet.talend.com | jvm | low | 1 |  |
| maven.shedaniel.me | jvm | low | 1 |  |
| maven.squiddev.cc | jvm | low | 1 |  |
| maven.terraformersmc.com | jvm | low | 1 |  |
| maven.tterrag.com | jvm | low | 1 |  |
| mavenrepo.openmrs.org | jvm | low | 1 |  |
| mavensync.zkoss.org | jvm | low | 1 |  |
| microsoft.pkgs.visualstudio.com | rust | low | 1 |  |
| mirror.baidubce.com | containers | low | 1 |  |
| mirrors.cnnic.cn | dart | low | 1 | non-configuration-evidence-only |
| mirrors.olares.cn | containers | low | 1 | non-configuration-evidence-only |
| mtkopone.github.com | jvm | low | 1 |  |
| mvn.devos.one | jvm | low | 1 |  |
| nexus.eryajf.net | go | low | 1 | non-configuration-evidence-only |
| nexus.protontech.ch | javascript | low | 1 |  |
| nexus.stirante.com | jvm | low | 1 |  |
| nova.laravel.com | php | low | 1 |  |
| npm.nordicsemi.no | javascript | low | 1 |  |
| npm.yzops.net | javascript | low | 1 |  |
| onejar-maven-plugin.googlecode.com | jvm | low | 1 |  |
| oss.jfrog.org | jvm | low | 1 |  |
| packages.confluent.io | jvm | low | 1 |  |
| packages.orekit.org | jvm | low | 1 |  |
| packages.vulnetix.com | erlang, julia | low | 1 | non-configuration-evidence-only |
| packagist.laravel-china.org | php | low | 1 |  |
| pypi.anaconda.org | python | low | 1 |  |
| pypi.collmot.com | python | low | 1 |  |
| pypi.epixstudios.co.uk | python | low | 1 |  |
| pypi.zama.ai | python | low | 1 |  |
| radiant-rstats.github.io | r | low | 1 |  |
| registry-npm.kaikeba.com | javascript | low | 1 |  |
| registry.cn-hangzhou.aliyuncs.com | containers | low | 1 |  |
| registry.gosub.io | rust | low | 1 |  |
| registry.npmjs.com | javascript | low | 1 |  |
| registry.tuist.dev | swift | low | 1 |  |
| releases.tongyuan.cc | julia | low | 1 |  |
| repo.codemc.org | jvm | low | 1 |  |
| repo.extendedclip.com | jvm | low | 1 |  |
| repo.gentics.com | jvm | low | 1 |  |
| repo.glaremasters.me | jvm | low | 1 |  |
| repo.itextsupport.com | dotnet | low | 1 |  |
| repo.magento.com | php | low | 1 |  |
| repo.radeon.com | python | low | 1 |  |
| repo.spongepowered.org | jvm | low | 1 |  |
| repository-dma.forge.cloudbees.com | jvm | low | 1 |  |
| repository.corporation.com | python | low | 1 |  |
| repository.mulesoft.org | jvm | low | 1 |  |
| repository.nexus.camunda.cloud | jvm | low | 1 |  |
| resources.knopflerfish.org | jvm | low | 1 |  |
| s01.oss.sonatype.org | jvm | low | 1 |  |
| scala-ci.typesafe.com | jvm | low | 1 |  |
| static.mediadrop.video | python | low | 1 |  |
| tuist.dev | swift | low | 1 |  |
| usw1.packages.broadcom.com | jvm | low | 1 |  |
| vd.kaikeba.com | javascript | low | 1 |  |
| wheels.cua.ai | python | low | 1 |  |
| wheels.fermentrack.com | python | low | 1 |  |
| wpackagist.org | php | low | 1 |  |
| www.cursemaven.com | jvm | low | 1 |  |
| www.eecs.berkeley.edu | jvm | low | 1 |  |
| www.sparetimelabs.com | jvm | low | 1 |  |
