angular
.module('module.webservice', [])
.factory("webservice", ['$http', '$rootScope', 'settings', 'messenger', 'staging_dir',
	function($http, $rootScope, settings, messenger, staging_dir) {

	let webservice = {};

	webservice.sec = {
		password: settings.password || ''
	};

    webservice.get = function(endpoint, method, data) {

        endpoint = angular.isArray(endpoint) ? settings[endpoint[0]] + endpoint[1] : settings.server_url + endpoint;
        method = method || "get";
        data = data || {};

        return new Promise(function(resolve, reject) {
            $http({
                method:	method,
                url: endpoint,
                data: data
            }).then(
                function(response) {
                    console.log("response", response);
                    if (response.data.success === false) {
                        messenger.error(response.message);
                        reject(response.message);
                    } else {
                        resolve(response.data);
                    }
                },
                function(err) {
                    if (angular.isDefined(err.data) && angular.isDefined(err.data.warnings)) {
                        err.data.warnings.forEach(messenger.warning);
                    }
                    let errText = endpoint + ": " + err.status + " " + err.statusText;
                    console.log(err);
                    if (angular.isDefined(err.data) && angular.isDefined(err.data.message)) {
                        errText = err.data.message;
                    }
                    messenger.error(errText);
                    reject(errText);
                }
            )
        })
    };


	return webservice;
}]);
