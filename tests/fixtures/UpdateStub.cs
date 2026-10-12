using System;
using System.IO;
class Stub {
    static int Main(string[] args) {
        string root = Environment.GetEnvironmentVariable("REUP_QA_UPDATE_ROOT");
        if (String.IsNullOrEmpty(root) || !File.Exists(Path.Combine(root, "qa-only.flag"))) return 4;
        string name = AppDomain.CurrentDomain.FriendlyName;
        File.WriteAllText(Path.Combine(root, name + ".result"), String.Join("\n", args));
        return 0;
    }
}
