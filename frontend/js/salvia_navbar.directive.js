angular
.module('directive.salviaNavbar', ['ng'] )
.directive('salviaNavbar' , ['steps', 'settings', function(steps, settings) {
    return {
        restrict: 'E',
        templateUrl: 'js/salvia_navbar.html',
        link: function(scope, elem, attrs) {
            scope.settings = settings;
            scope.views = steps.views;
            scope.changeView = steps.changeView;
            scope.getCurrentView = () => steps.current;
        }
    }
}]);
