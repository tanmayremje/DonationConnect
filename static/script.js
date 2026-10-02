// ---------------------------------------------
// AUTO HIDE FLASH MESSAGES
// ---------------------------------------------

setTimeout(function () {

    const messages =
        document.querySelectorAll(".flash");

    messages.forEach(function (message) {

        message.style.opacity = "0";

        setTimeout(function () {
            message.remove();
        }, 500);

    });

}, 4000);


// ---------------------------------------------
// BROWSER GEOLOCATION
// ---------------------------------------------

function getLocation() {

    const status =
        document.getElementById("locationStatus");

    const locationInput =
        document.getElementById("location");

    if (!navigator.geolocation) {

        status.innerHTML =
            "Geolocation is not supported by your browser.";

        return;
    }

    status.innerHTML =
        "Getting your location...";


    navigator.geolocation.getCurrentPosition(

        function (position) {

            const latitude =
                position.coords.latitude;

            const longitude =
                position.coords.longitude;


            /*
             * The browser provides coordinates.
             * Nominatim can then reverse-geocode
             * them into a readable address.
             */

            fetch(
                "https://nominatim.openstreetmap.org/reverse?" +
                new URLSearchParams({
                    lat: latitude,
                    lon: longitude,
                    format: "json"
                }),
                {
                    headers: {
                        "Accept": "application/json"
                    }
                }
            )

            .then(response => response.json())

            .then(data => {

                if (data.display_name) {

                    locationInput.value =
                        data.display_name;

                    status.innerHTML =
                        "✓ Current location added.";

                }

            })

            .catch(() => {

                status.innerHTML =
                    "Location found, but address could not be loaded.";

            });

        },

        function () {

            status.innerHTML =
                "Unable to get your location.";

        }

    );

}

function showNotificationPopup(title, message) {

    document.getElementById("notificationTitle").innerText = title;

    document.getElementById("notificationMessage").innerText = message;

    const popup = document.getElementById("notificationPopup");

    popup.style.display = "flex";

    // Automatically hide after 5 seconds
    setTimeout(function() {

        closeNotificationPopup();

    }, 5000);
}


function closeNotificationPopup() {

    document.getElementById("notificationPopup").style.display = "none";

}  

function checkNotifications() {

    fetch("/get-notifications")
        .then(response => response.json())
        .then(data => {

            if (data.length > 0) {

                const notification = data[0];

                showNotificationPopup(
                    "🔔 New Donation Request",
                    notification.message
                );

            }

        })
        .catch(error => {
            console.log("Notification error:", error);
        });
}
