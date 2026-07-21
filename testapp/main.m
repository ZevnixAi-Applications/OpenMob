// OpenMob debugger testbed: a counter app whose timer `tick:` fires every 2s,
// giving debug sessions a breakpoint that triggers without any UI interaction.
// Build with testapp/build.sh (simulator only).
#import <UIKit/UIKit.h>

@interface ViewController : UIViewController
@property(nonatomic, strong) UILabel *label;
@property(nonatomic, assign) int count;
@end

@implementation ViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = [UIColor systemBackgroundColor];
    self.label = [[UILabel alloc] initWithFrame:self.view.bounds];
    self.label.textAlignment = NSTextAlignmentCenter;
    self.label.font = [UIFont monospacedDigitSystemFontOfSize:48 weight:UIFontWeightBold];
    self.label.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.view addSubview:self.label];
    [NSTimer scheduledTimerWithTimeInterval:2.0
                                     target:self
                                   selector:@selector(tick:)
                                   userInfo:nil
                                    repeats:YES];
    [self tick:nil];
}

- (void)tick:(NSTimer *)timer {
    int next = self.count + 1;
    self.count = next;
    self.label.text = [NSString stringWithFormat:@"tick %d", next];
}

@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation AppDelegate

- (BOOL)application:(UIApplication *)application
    didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    self.window = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
    self.window.rootViewController = [ViewController new];
    [self.window makeKeyAndVisible];
    return YES;
}

@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }
}
