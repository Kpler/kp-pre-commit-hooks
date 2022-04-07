# Set up the project with nix
# cf https://github.com/Kpler/ct-webserver#option-2-using-nix
let
  jdk = pkgs.openjdk11;

  nixpkgs = builtins.fetchTarball {
    name   = "nixos-21.05";
    url    = "https://github.com/NixOS/nixpkgs/archive/1f91fd104066.tar.gz";
    sha256 = "1lcfcwgal9fpaiq71981abyzz160r6nx1y4pyy1dnvaf951xkdcj";
  };

  pkgs = import nixpkgs { };
in
  pkgs.mkShell {
    buildInputs = [
      pkgs.pre-commit
    ];
  }
