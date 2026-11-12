// A check that refuses whatever it is given: restore-graph must leave the live database untouched.
public class FailingCheck {
  public static void main(String[] args) {
    System.err.println("does not open: refused by the test's own check");
    System.exit(1);
  }
}
