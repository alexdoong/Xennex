using System;

namespace WacomRealController
{
    public class WuWaSubstat
    {
        public string Name  = "";
        public string Value = "";
        public int Quality  = 0; // 0=unrated 1=great 2=good 3=ok 4=bad
    }

    public class WuWaEcho
    {
        public string Name          = "";
        public string ImagePath     = "";
        public string MainStatName  = "ATK%";
        public string MainStatValue = "0%";
        public WuWaSubstat[] Substats = new WuWaSubstat[5];
        public WuWaEcho() { for (int i = 0; i < 5; i++) Substats[i] = new WuWaSubstat(); }
    }

    public class WuWaBuild
    {
        public string ResonatorName  = "Resonator Name";
        public string Level          = "90/90";
        public string Element        = "Spectro";
        public int    Sequence       = 0;
        public string CharImagePath  = "";
        public int    ImagePanX      = 0;
        public int    ImagePanY      = 0;
        public float  ImageScale     = 1.0f;
        public string WeaponName     = "Weapon Name";
        public int    WeaponRarity   = 5;
        public int    WeaponRefinement = 1;
        public string WeaponLevel    = "90/90";
        public string WeaponImagePath = "";
        public string StatHP         = "0";
        public string StatATK        = "0";
        public string StatDEF        = "0";
        public string StatCritRate   = "0.0%";
        public string StatCritDMG    = "0.0%";
        public string StatEnergyRegen = "100%";
        public string StatSklDMG     = "0%";
        public WuWaEcho[] Echoes     = new WuWaEcho[5];
        public WuWaBuild() { for (int i = 0; i < 5; i++) Echoes[i] = new WuWaEcho(); }
    }
}
